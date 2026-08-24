"""Motion subgraph — 3D motion analysis with ReAct reasoning chain."""
import logging
from typing import Any, Literal

from langgraph.graph import StateGraph, END

from app.graph.prompt_builder import PromptBuilder
from app.graph.safety_policy import compose_safe_prompt
from app.graph.state import RouterState, record_execution
from app.graph.structured_state import add_tool_preview

logger = logging.getLogger(__name__)


def _format_motion_metrics(metrics: Any) -> str:
    """Format existing structured metrics without inventing missing evidence."""
    if not isinstance(metrics, dict):
        return ""

    metric_items = [
        ("DTW", metrics.get("dtw_distance")),
        ("余弦相似度", metrics.get("cosine_similarity")),
        ("形状差异", metrics.get("shape_difference")),
    ]
    present_metrics = [f"{name}={value}" for name, value in metric_items if value is not None]
    lines = [f"  · 对比指标：{'，'.join(present_metrics)}"] if present_metrics else []

    labels = metrics.get("labels")
    if isinstance(labels, dict):
        label_items = [
            ("DTW", labels.get("dtw")),
            ("余弦", labels.get("cosine")),
            ("形状", labels.get("shape")),
        ]
        present_labels = [f"{name}={value}" for name, value in label_items if value is not None]
        if present_labels:
            lines.append(f"  · 项目启发式标签：{'，'.join(present_labels)}")
    if metrics.get("overall_verdict"):
        lines.append(f"  · 汇总结论：{metrics['overall_verdict']}")

    quality = metrics.get("quality")
    if isinstance(quality, dict):
        lines.append(
            "  · 质量门控："
            f"accepted={quality.get('accepted', '未知')}，"
            f"有效对齐比例={quality.get('valid_alignment_ratio', '未知')}，"
            f"最低比例={quality.get('min_valid_alignment_ratio', '未知')}"
        )

    joint_distance = metrics.get("joint_distance")
    if isinstance(joint_distance, dict):
        worst_joint = joint_distance.get("worst_joint")
        if isinstance(worst_joint, dict):
            lines.append(
                "  · 平均偏差最大的关节："
                f"索引 {worst_joint.get('joint_index', '未知')}，"
                f"平均距离 {worst_joint.get('mean_distance', '未知')}"
            )
        worst_point = joint_distance.get("worst_aligned_point")
        if isinstance(worst_point, dict):
            lines.append(
                "  · 最大单点偏差："
                f"关节索引 {worst_point.get('joint_index', '未知')}，"
                f"用户帧 {worst_point.get('user_frame', '未知')}，"
                f"参考帧 {worst_point.get('reference_frame', '未知')}，"
                f"用户时间 {worst_point.get('user_time_seconds', '未知')} 秒，"
                f"参考时间 {worst_point.get('reference_time_seconds', '未知')} 秒，"
                f"距离 {worst_point.get('distance', '未知')}"
            )

    angle_errors = metrics.get("joint_angle_errors")
    if isinstance(angle_errors, dict):
        worst_angle = angle_errors.get("worst")
        if isinstance(worst_angle, dict):
            frame = worst_angle.get("max_error_frame")
            frame = frame if isinstance(frame, dict) else {}
            lines.append(
                "  · 最大关节角误差："
                f"{worst_angle.get('joint', '未知')}，"
                f"最大 {worst_angle.get('max_error_degrees', '未知')} 度，"
                f"平均 {worst_angle.get('mean_error_degrees', '未知')} 度，"
                f"用户帧 {frame.get('user_frame', '未知')}，"
                f"参考帧 {frame.get('reference_frame', '未知')}，"
                f"用户时间 {frame.get('user_time_seconds', '未知')} 秒，"
                f"参考时间 {frame.get('reference_time_seconds', '未知')} 秒"
            )

    return ("\n".join(lines) + "\n") if lines else ""


def think_node(state: RouterState) -> RouterState:
    """Think node: LLM analyzes user intent, decides which tools to use."""
    from app.config import config
    from app.llm.providers import create_llm
    from app.tools.motion_tool import list_motion_library

    library_result = list_motion_library(config.motion_library_dir)
    lib_data = library_result.data if library_result.ok else {}
    lib_names = ", ".join(lib_data.keys()) if lib_data else "无已加载的标准动作"

    prompt = f"""# 角色
你是一位 3D 运动分析专家，专长于使用计算机视觉和姿态估计算法评估健身动作质量。

# 任务
分析用户的问题，制定动作评估计划。

# 分析要点
1. 用户想要分析什么动作？（如深蹲、硬拉、卧推）
2. 应该评估哪些关键技术指标？（如膝关节角度、背部倾斜度、重心位移）
3. 动作库中有哪些可用的标准参考动作？
4. 如果没有标准参考动作，如何进行独立评估？

# 可用标准动作
{lib_names}

# 用户输入
{state['user_input']}

请用中文输出你的分析计划："""
    prompt = compose_safe_prompt(prompt, kind="motion.plan")

    llm = create_llm(
        state.get("_model_id"),
        max_tokens=512,
        temperature=0.3,
    )
    thought = llm.generate(prompt)
    state["_thought"] = thought  # type: ignore
    state["_iteration"] = state.get("_iteration", 0)  # type: ignore
    return state


def parse_node(state: RouterState) -> RouterState:
    """Parse node: resolve which tools and parameters are needed."""
    from app.tools.motion_tool import list_motion_library
    from app.config import config

    library_result = list_motion_library(config.motion_library_dir)
    lib_data = library_result.data if library_result.ok else {}
    user_input = state["user_input"]
    tools_to_call = []
    artifact_results = [
        {
            "type": "media_artifact",
            "artifact_id": artifact.get("id", ""),
            "media_type": artifact.get("media_type", ""),
            "filename": artifact.get("filename", ""),
            "payload": artifact.get("payload", {}),
        }
        for artifact in state.get("_motion_artifacts", [])
    ]

    for name, path in lib_data.items():
        if name in user_input:
            tools_to_call.append({
                "tool": "compare_with_library",
                "ref_name": name,
                "ref_path": path,
            })

    if ".npz" in user_input:
        for word in user_input.split():
            if word.endswith(".npz") or ".npz" in word:
                tools_to_call.append({
                    "tool": "load_user_pose",
                    "file_path": word.strip(",.;!?"),
                })
                break

    state["_tools_to_call"] = tools_to_call  # type: ignore
    state["_tool_results"] = artifact_results
    state["_parse_done"] = True  # type: ignore
    record_execution(
        state,
        "motion",
        "media_artifact_analysis" if artifact_results else (
            "npz_analysis" if tools_to_call else "guidance_only"
        ),
        degraded=not bool(tools_to_call or artifact_results),
        detail=(
            "No uploaded pose data was available"
            if not tools_to_call and not artifact_results
            else ""
        ),
    )
    return state


def tool_node(state: RouterState) -> RouterState:
    """Tool node: execute actual pose analysis computations."""
    from app.tools.motion_tool import load_npz_pose, compute_similarity

    tools_to_call = state.get("_tools_to_call", [])  # type: ignore
    results = list(state.get("_tool_results", []))

    for tool_call in tools_to_call:
        if tool_call["tool"] == "load_user_pose":
            try:
                pose_result = load_npz_pose(tool_call["file_path"])
                if not pose_result.ok:
                    results.append({"type": "error", "message": pose_result.error_message})
                    continue
                pose = pose_result.data
                results.append({
                    "type": "load_pose",
                    "file": tool_call["file_path"],
                    "frames": pose.shape[0],
                    "joints": pose.shape[1],
                })
                state["_user_pose"] = pose  # type: ignore
            except Exception as e:
                results.append({"type": "error", "message": str(e)})

        elif tool_call["tool"] == "compare_with_library":
            try:
                ref_result = load_npz_pose(tool_call["ref_path"])
                if not ref_result.ok:
                    results.append({"type": "error", "message": ref_result.error_message})
                    continue
                ref_pose = ref_result.data
                user_pose = state.get("_user_pose")  # type: ignore
                if user_pose is not None:
                    metrics_result = compute_similarity(user_pose, ref_pose)
                    if metrics_result.ok:
                        metrics = metrics_result.data
                    else:
                        results.append({"type": "error", "message": metrics_result.error_message})
                        continue
                    results.append({
                        "type": "comparison",
                        "reference": tool_call["ref_name"],
                        "metrics": metrics,
                    })
            except Exception as e:
                results.append({"type": "error", "message": str(e)})

    state["_tool_results"] = results  # type: ignore
    if results:
        summary_lines = []
        for item in results[:4]:
            if item.get("type") == "load_pose":
                summary_lines.append(
                    f"loaded_pose:{item.get('frames')} frames/{item.get('joints')} joints"
                )
            elif item.get("type") == "comparison":
                metrics = item.get("metrics", {})
                summary_lines.append(
                    f"comparison:{item.get('reference')} "
                    f"dtw={metrics.get('dtw_distance')} "
                    f"cos={metrics.get('cosine_similarity')} "
                    f"shape={metrics.get('shape_difference')}"
                )
            elif item.get("type") == "error":
                summary_lines.append(f"error:{item.get('message')}")
            elif item.get("type") == "media_artifact":
                payload = item.get("payload", {})
                summary_lines.append(
                    f"media_artifact:{item.get('media_type')} "
                    f"frames={payload.get('frames')} joints={payload.get('joints')}"
                )
        add_tool_preview(
            state,
            intent="motion",
            tool="motion.analysis",
            summary="\n".join(summary_lines),
            data_ref="_tool_results",
        )
    logger.info(f"Tool execution complete: {len(results)} results")
    return state


def check_node(state: RouterState) -> RouterState:
    """Check node: evaluate results and produce final answer."""
    from app.config import config
    from app.llm.providers import create_llm

    tool_results = state.get("_tool_results", [])  # type: ignore

    if not tool_results:
        prompt = f"""# 角色
你是一名运动生物力学教练，擅长分析健身动作的关节力线和姿态质量。

# 情况说明
用户想了解动作分析相关的内容，但当前请求没有可供分析的图片、视频或结构化姿态数据。

# 回答要求
1. 根据你的健身知识，对用户提到的动作给出技术要点说明。
2. 告知用户可以直接上传图片或视频；系统内部会用 MediaPipe 提取 PoseSequence。.npz（T×J×3）主要是标准动作库、调试和评测格式，不要求普通用户手工制作。
3. 准确说明当前能力：可提取姿态序列；选择兼容标准样本后，可计算 FastDTW、余弦相似度、对齐后的逐关节距离以及 MediaPipe 33 点下的膝/髋角度误差，并执行置信度质量门控。
4. 说明当前边界：尚未实现完整专业动作评分、动作周期切分和专项阶段规则；没有数据或兼容参考样本时，不输出具体纠错结论。
5. 不做无根据的推测——没有数据就不瞎猜用户动作的问题。

# 用户问题
{state['user_input']}

请给出有帮助的回复："""
    else:
        results_text = ""
        for r in tool_results:
            if r["type"] == "load_pose":
                results_text += f"- 已加载姿态数据: {r['frames']}帧, {r['joints']}个关键点\n"
            elif r["type"] == "comparison":
                m = r["metrics"]
                results_text += f"- 与标准动作'{r['reference']}'对比:\n"
                results_text += _format_motion_metrics(m)
            elif r["type"] == "error":
                results_text += f"- 错误: {r['message']}\n"
            elif r["type"] == "media_artifact":
                payload = r.get("payload", {})
                results_text += (
                    f"- 已上传{r.get('media_type', '媒体')}：{r.get('filename', '')}\n"
                    f"  · 姿态序列：{payload.get('frames', '未知')}帧，"
                    f"{payload.get('joints', '未知')}个关键点\n"
                    f"  · 姿态模型：{payload.get('pose_model', '未知')}，"
                    f"关节定义：{payload.get('joint_schema', '未知')}\n"
                )
                if payload.get("valid_frame_ratio") is not None:
                    results_text += (
                        f"  · 有效姿态帧比例：{payload['valid_frame_ratio']}\n"
                    )
                confidence = payload.get("confidence_summary")
                if isinstance(confidence, dict):
                    results_text += (
                        f"  · 关键点平均置信度：{confidence.get('mean', '未知')}\n"
                    )
                if payload.get("reference"):
                    results_text += f"  · 标准动作：{payload['reference']}\n"
                metrics = payload.get("metrics")
                if isinstance(metrics, dict):
                    results_text += _format_motion_metrics(metrics)
                for warning in payload.get("warnings", [])[:3]:
                    results_text += f"  · 注意：{warning}\n"

        prompt = f"""# 角色
你是一名运动生物力学教练，正在解读 3D 动作分析结果。

# 分析结果
{results_text}

# 指标说明
- **DTW距离**：衡量时序对齐后的整体姿态差异（越小越接近）
- **余弦相似度**：衡量整体姿态方向的相似性（>0.85为优秀，需结合其他指标）
- **形状差异**：衡量对齐后逐关节位置的平均偏差（越小越接近）
- 0.3、0.85、0.2 是项目原型的启发式阈值，只用于相对比较，不是医学或专业教练评分标准

# 用户问题
{state['user_input']}

# 分析计划
{state.get('_thought', '')}

# 回答要求
1. 先用通俗语言总结当前实际提供的分析结果；只有结果中存在对比指标时，才解释 DTW、余弦相似度和形状差异，不得补写缺失指标。
2. 只有结构化结果给出了关节、帧、时间或角度证据时，才指出对应的具体问题并给出改进建议；证据不足时明确说明不能定位，不得猜测。
3. 仅当质量门控未拒绝、三个指标均实际存在且都很好（DTW<0.3, 余弦>0.85, 形状差<0.2）时，直接表扬并鼓励继续训练。
4. 如果指标之间矛盾（如DTW好但形状差大），分析可能的原因。
5. 如果质量门控 accepted=false，优先提示重新拍摄，不给确定性动作结论。

请给出分析报告："""

    prompt = PromptBuilder.attach(
        state,
        prompt,
        kind="motion.answer",
        sections=["motion_evidence", "motion_plan", "user_question"],
    )
    if state.get("_streaming"):
        state["result"] = ""
        state["_check_pass"] = True  # type: ignore
        return state

    llm = create_llm(
        state.get("_model_id"),
        max_tokens=config.model_max_tokens,
    )
    answer = llm.generate(prompt)
    state["result"] = answer
    state["_check_pass"] = True  # type: ignore
    return state


def should_continue(state: RouterState) -> Literal["tool", "check"]:
    """Decide: continue to tool execution or proceed to check."""
    tools_to_call = state.get("_tools_to_call", [])  # type: ignore
    iteration = state.get("_iteration", 0)  # type: ignore
    from app.config import config

    if tools_to_call and iteration < config.react_max_iterations:
        state["_iteration"] = iteration + 1  # type: ignore
        return "tool"
    return "check"


def build_motion_subgraph():
    """Build Motion subgraph: think -> parse -> tool -> check (ReAct loop)."""
    builder = StateGraph(RouterState)
    builder.add_node("think", think_node)
    builder.add_node("parse", parse_node)
    builder.add_node("tool", tool_node)
    builder.add_node("check", check_node)

    builder.set_entry_point("think")
    builder.add_edge("think", "parse")
    builder.add_conditional_edges(
        "parse",
        should_continue,
        {"tool": "tool", "check": "check"},
    )
    builder.add_edge("tool", "check")
    builder.add_edge("check", END)

    return builder.compile()
