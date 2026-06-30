"""Motion subgraph — 3D motion analysis with ReAct reasoning chain."""
import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState

logger = logging.getLogger(__name__)


def think_node(state: RouterState) -> RouterState:
    """Think node: LLM analyzes user intent, decides which tools to use."""
    from app.config import config
    from app.llm.loader import LLMLoader
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

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
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
    state["_parse_done"] = True  # type: ignore
    return state


def tool_node(state: RouterState) -> RouterState:
    """Tool node: execute actual pose analysis computations."""
    from app.tools.motion_tool import load_npz_pose, compute_similarity

    tools_to_call = state.get("_tools_to_call", [])  # type: ignore
    results = []

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
    logger.info(f"Tool execution complete: {len(results)} results")
    return state


def check_node(state: RouterState) -> RouterState:
    """Check node: evaluate results and produce final answer."""
    from app.config import config
    from app.llm.loader import LLMLoader

    tool_results = state.get("_tool_results", [])  # type: ignore

    if not tool_results:
        prompt = f"""# 角色
你是一名运动生物力学教练，擅长分析健身动作的关节力线和姿态质量。

# 情况说明
用户想了解动作分析相关的内容，但目前没有上传 3D 姿态数据文件（.npz 格式）。

# 回答要求
1. 根据你的健身知识，对用户提到的动作给出技术要点说明。
2. 告知用户如何获取 3D 姿态数据：可以使用 MediaPipe、OpenPose 等工具从视频中提取人体关键点，保存为 .npz 格式（形状为 T×J×3，T=帧数，J=关键点数，3=x/y/z 坐标）。
3. 说明系统支持的分析功能：单动作姿态质量评分、与标准动作库对比、关节角度分析、动作节奏评估。
4. 不做无根据的推测——没有数据就不瞎猜用户动作的问题。

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
                results_text += f"  · DTW距离(节奏差异): {m['dtw_distance']}（越小越接近）\n"
                results_text += f"  · 余弦相似度(姿态方向): {m['cosine_similarity']}（越接近1越相似）\n"
                results_text += f"  · 形状差异(幅度差异): {m['shape_difference']}（越小越接近）\n"
            elif r["type"] == "error":
                results_text += f"- 错误: {r['message']}\n"

        prompt = f"""# 角色
你是一名运动生物力学教练，正在解读 3D 动作分析结果。

# 分析结果
{results_text}

# 指标说明
- **DTW距离**：衡量动作节奏与标准动作的差异（越小越好，<0.3为优秀）
- **余弦相似度**：衡量整体姿态方向的相似性（>0.85为优秀，需结合其他指标）
- **形状差异**：衡量动作幅度和关节轨迹的偏差（越小越好，<0.2为优秀）

# 用户问题
{state['user_input']}

# 分析计划
{state.get('_thought', '')}

# 回答要求
1. 先用通俗语言总结三个指标的含义和用户动作的整体评价。
2. 指出最突出的问题（如果有），给出具体改进建议。
3. 如果三个指标都很好（DTW<0.3, 余弦>0.85, 形状差<0.2），直接表扬并鼓励继续训练。
4. 如果指标之间矛盾（如DTW好但形状差大），分析可能的原因。

请给出分析报告："""

    state["_prompt"] = prompt  # type: ignore
    if state.get("_streaming"):
        state["result"] = ""
        state["_check_pass"] = True  # type: ignore
        return state

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
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
