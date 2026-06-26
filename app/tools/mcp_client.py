"""MCP protocol client — subprocess + stdio JSON-RPC.

PERMISSION: This tool connects to external MCP servers via subprocess.
It must NOT execute arbitrary system commands — only the configured
server_command is launched. Tool names and arguments from the model are
validated before being forwarded to the MCP server.
"""

import json
import logging
import subprocess
import uuid
from typing import Any, Dict, List, Optional

from app.tools.types import (
    ToolResult,
    ErrorCode,
    check_str_nonempty,
)

logger = logging.getLogger(__name__)


class MCPClient:
    """Lightweight MCP client using subprocess + stdio JSON-RPC.

    Input:
        connect():    no params
        list_tools(): no params
        call_tool():  tool_name: str, arguments: dict[str, any]

    Output:
        All methods return ToolResult.
        ToolResult.data matches the MCP server response shape.
        ToolResult.meta = {"is_mock": bool} when mock mode.

    Demo mode: server_command="mock" uses preset recipe data.
    """

    def __init__(self, server_command: str):
        self.server_command = server_command
        self._process: Optional[subprocess.Popen] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> ToolResult:
        """Start MCP server subprocess and complete initialize handshake."""
        if self.server_command == "mock":
            self._connected = True
            logger.info("MCP Client in mock mode")
            return ToolResult.ok(connected=True, is_mock=True)

        resolved = self._resolve_command(self.server_command)
        if resolved is None:
            self._connected = False
            return ToolResult.fail(
                ErrorCode.DATA_NOT_FOUND,
                f"MCP server command not found: '{self.server_command}'. "
                f"Install it (e.g., 'npm install -g {self.server_command}') "
                f"or set mcp_server_command to 'mock' for demo recipes.",
                meta={"server_command": self.server_command},
            )

        try:
            self._process = subprocess.Popen(
                [resolved],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            init_request = self._build_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "fitness-assistant", "version": "0.1.0"},
            })
            response = self._send_request(init_request)
            if response is None:
                self._connected = False
                return ToolResult.fail(
                    ErrorCode.NETWORK_ERROR,
                    f"MCP server '{self.server_command}' started but initialize "
                    f"handshake failed (no response)",
                    meta={"server_command": self.server_command},
                )
            # Send initialized notification per MCP spec
            initialized_notification = self._build_request(
                "notifications/initialized", {}
            )
            self._send_request(initialized_notification)
            self._connected = True
            logger.info(f"MCP connected to {self.server_command} (resolved={resolved})")
            return ToolResult.ok(
                connected=True,
                server_command=self.server_command,
                resolved_path=resolved,
                is_mock=False,
            )
        except FileNotFoundError:
            self._connected = False
            return ToolResult.fail(
                ErrorCode.DATA_NOT_FOUND,
                f"MCP server command not found: '{self.server_command}' "
                f"(resolved as '{resolved}'). "
                f"Install it (e.g., 'npm install -g {self.server_command}') "
                f"or set mcp_server_command to 'mock' for demo recipes.",
                meta={"server_command": self.server_command},
            )
        except Exception as e:
            self._connected = False
            logger.error(f"MCP connect failed: {e}")
            return ToolResult.fail(
                ErrorCode.INTERNAL_ERROR,
                f"Failed to start MCP server: {e}",
                meta={"server_command": self.server_command},
            )

    def disconnect(self) -> ToolResult:
        """Terminate MCP server subprocess."""
        try:
            if self._process:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._process = None
            self._connected = False
            return ToolResult.ok(disconnected=True)
        except Exception as e:
            return ToolResult.fail(
                ErrorCode.INTERNAL_ERROR,
                f"Error during disconnect: {e}",
            )

    def list_tools(self) -> ToolResult:
        """Get available tools from MCP server."""
        if self.server_command == "mock":
            return ToolResult.ok(
                data=[
                    {
                        "name": "mcp_howtocook_getAllRecipes",
                        "description": "获取所有菜谱",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "no_param": {"type": "string", "description": "无参数"},
                            },
                        },
                    },
                    {
                        "name": "mcp_howtocook_getRecipesByCategory",
                        "description": "根据分类查询菜谱，可选分类: 水产, 早餐, 调料, 甜品, 饮品, 荤菜, 半成品加工, 汤, 主食, 素菜",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": [
                                        "水产", "早餐", "调料", "甜品", "饮品",
                                        "荤菜", "半成品加工", "汤", "主食", "素菜",
                                    ],
                                    "description": "菜谱分类名称",
                                },
                            },
                            "required": ["category"],
                        },
                    },
                    {
                        "name": "mcp_howtocook_recommendMeals",
                        "description": "根据用户的忌口、过敏原、人数智能推荐菜谱，创建一周的膳食计划及购物清单",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "allergies": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "过敏原列表，如[\"虾\"]",
                                },
                                "avoidItems": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "忌口食材列表，如[\"葱\", \"姜\"]",
                                },
                                "peopleCount": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 10,
                                    "description": "用餐人数 1-10",
                                },
                            },
                            "required": ["peopleCount"],
                        },
                    },
                    {
                        "name": "mcp_howtocook_whatToEat",
                        "description": "不知道吃什么？根据人数推荐适合的菜品组合",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "peopleCount": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 10,
                                    "description": "用餐人数 1-10",
                                },
                            },
                            "required": ["peopleCount"],
                        },
                    },
                    {
                        "name": "mcp_howtocook_getRecipeById",
                        "description": "根据菜谱名称查询指定菜谱的完整详情，包括食材、步骤等",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "菜谱名称，支持模糊匹配",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                ],
                is_mock=True,
            )

        if not self._connected:
            return ToolResult.fail(
                ErrorCode.NETWORK_ERROR,
                "Not connected to MCP server. Call connect() first.",
            )

        request = self._build_request("tools/list", {})
        response = self._send_request(request)
        if response is None:
            return ToolResult.fail(
                ErrorCode.NETWORK_ERROR,
                "MCP server did not respond to tools/list request",
            )
        if "error" in response:
            return ToolResult.fail(
                ErrorCode.INTERNAL_ERROR,
                f"MCP error: {response['error']}",
                data=response,
            )
        return ToolResult.ok(
            data=response.get("result", {}).get("tools", []),
            is_mock=False,
        )

    def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        """Call a specific tool on the MCP server.

        Args:
            tool_name: Name of the tool (must be non-empty string).
            arguments: Tool parameters (must be a dict, not None).
        """
        # --- Input validation ---
        err = check_str_nonempty(tool_name, "tool_name")
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)
        if not isinstance(arguments, dict):
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                f"'arguments' must be a dict, got {type(arguments).__name__}",
            )

        # --- Mock mode ---
        if self.server_command == "mock":
            raw_data = self._mock_tool_call(tool_name, arguments)
            parsed = self._extract_mcp_content(raw_data)
            return ToolResult.ok(data=parsed, is_mock=True)

        # --- Connected check ---
        if not self._connected:
            return ToolResult.fail(
                ErrorCode.NETWORK_ERROR,
                "MCP client not connected. Call connect() first.",
                meta={"tool_name": tool_name},
            )

        # --- Send request ---
        request = self._build_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        response = self._send_request(request)

        if response is None:
            return ToolResult.fail(
                ErrorCode.NETWORK_ERROR,
                f"MCP server did not respond to tools/call for '{tool_name}'",
                meta={"tool_name": tool_name},
            )

        if "error" in response:
            return ToolResult.fail(
                ErrorCode.INTERNAL_ERROR,
                f"MCP server error: {response['error']}",
                data=response,
                meta={"tool_name": tool_name},
            )

        raw_result = response.get("result", {})
        parsed = self._extract_mcp_content(raw_result)
        return ToolResult.ok(data=parsed, is_mock=False)

    # --- Private helpers ---

    @staticmethod
    def _resolve_command(server_command: str) -> Optional[str]:
        """Resolve server_command to an absolute executable path.

        Tries in order:
          1. server_command as-is (works for absolute paths and PATH entries)
          2. On Windows: server_command + '.cmd' extension
          3. npm global prefix (from 'npm config get prefix')
        """
        import os
        import shutil

        # absolute path or PATH entry — return full resolved path
        resolved = shutil.which(server_command)
        if resolved:
            return resolved

        # Windows: try .cmd extension
        if os.name == "nt":
            cmd = server_command + ".cmd"
            resolved = shutil.which(cmd)
            if resolved:
                return resolved

        # npm global prefix
        try:
            result = subprocess.run(
                ["npm", "config", "get", "prefix"],
                capture_output=True, text=True, timeout=5,
                encoding="utf-8",
            )
            prefix = result.stdout.strip()
            if prefix:
                candidate = os.path.join(prefix, server_command)
                if os.name == "nt":
                    candidate += ".cmd"
                if os.path.isfile(candidate):
                    return candidate
        except Exception:
            pass

        return None

    def _build_request(
        self, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }

    def _send_request(
        self, request: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if not self._process or not self._process.stdin:
            return None
        try:
            request_str = json.dumps(request) + "\n"
            self._process.stdin.write(request_str)
            self._process.stdin.flush()
            response_line = self._process.stdout.readline()
            return json.loads(response_line)
        except json.JSONDecodeError as e:
            logger.error(f"MCP invalid JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"MCP request failed: {e}")
            return None

    def _extract_mcp_content(self, raw: Dict[str, Any]) -> Any:
        """Extract parsed data from MCP content blocks.

        MCP standard: result.content is an array of {type, text} blocks.
        Tries to parse content[0].text as JSON; falls back to raw string
        or the original dict.
        """
        content_blocks = raw.get("content", [])
        if content_blocks and isinstance(content_blocks, list):
            first_text = content_blocks[0].get("text", "")
            try:
                return json.loads(first_text)
            except (json.JSONDecodeError, TypeError):
                return first_text
        return raw

    def _mock_tool_call(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mock MCP tool calls with preset Chinese recipe data."""
        import json as _json

        # --- mcp_howtocook_getRecipeById ---
        if tool_name == "mcp_howtocook_getRecipeById":
            query = arguments.get("query", "")
            recipes = {
                "番茄炒蛋": {
                    "name": "番茄炒蛋",
                    "ingredients": [
                        {"name": "番茄", "text_quantity": "番茄 2个"},
                        {"name": "鸡蛋", "text_quantity": "鸡蛋 3个"},
                        {"name": "葱", "text_quantity": "葱 适量"},
                        {"name": "盐", "text_quantity": "盐 适量"},
                        {"name": "糖", "text_quantity": "糖 少许"},
                        {"name": "食用油", "text_quantity": "食用油 适量"},
                    ],
                    "steps": [
                        "1. 番茄洗净切小块，鸡蛋打散加少许盐",
                        "2. 热锅加油，倒入蛋液，炒至凝固盛出",
                        "3. 锅中再加少许油，放入番茄块翻炒至出汁",
                        "4. 倒回鸡蛋，加盐和糖调味，撒葱花出锅",
                    ],
                    "description": "经典家常菜，新手友好，15分钟搞定",
                    "calories": "约250大卡/份",
                },
                "可乐鸡翅": {
                    "name": "可乐鸡翅",
                    "ingredients": [
                        {"name": "鸡翅中", "text_quantity": "鸡翅中 10个"},
                        {"name": "可乐", "text_quantity": "可乐 200ml"},
                        {"name": "生姜", "text_quantity": "生姜 3片"},
                        {"name": "料酒", "text_quantity": "料酒 1勺"},
                        {"name": "生抽", "text_quantity": "生抽 1勺"},
                    ],
                    "steps": [
                        "1. 鸡翅洗净，两面划两刀，加料酒腌制10分钟",
                        "2. 冷水下锅焯水去血沫，捞出沥干",
                        "3. 热锅少油，鸡翅煎至两面金黄",
                        "4. 倒入可乐，加生抽，大火烧开转小火炖15分钟",
                        "5. 大火收汁，汤汁浓稠裹住鸡翅即可出锅",
                    ],
                    "description": "可乐鸡翅色泽红亮，口感嫩滑，新手必学",
                    "calories": "约400大卡/份",
                },
            }
            for key, recipe in recipes.items():
                if key in query:
                    return {"content": [{"type": "text", "text": _json.dumps(recipe, ensure_ascii=False)}]}
            return {"content": [{"type": "text", "text": _json.dumps({
                "error": "未找到匹配的菜谱",
                "query": query,
                "suggestion": "请尝试其他菜谱名称或使用分类查询",
            }, ensure_ascii=False)}]}

        # --- mcp_howtocook_getRecipesByCategory ---
        elif tool_name == "mcp_howtocook_getRecipesByCategory":
            category = arguments.get("category", "")
            mock_data = {
                "荤菜": [
                    {"name": "可乐鸡翅", "description": "色泽红亮，口感嫩滑"},
                    {"name": "红烧肉", "description": "肥而不腻，入口即化"},
                ],
                "素菜": [
                    {"name": "番茄炒蛋", "description": "经典家常快手菜"},
                    {"name": "酸辣土豆丝", "description": "开胃下饭，酸辣爽脆"},
                ],
                "汤": [
                    {"name": "番茄蛋花汤", "description": "家常快手汤品"},
                    {"name": "紫菜蛋花汤", "description": "清淡鲜美"},
                ],
            }
            result = mock_data.get(category, [{"name": f"{category}示例菜谱", "description": "暂无更多数据"}])
            return {"content": [{"type": "text", "text": _json.dumps(result, ensure_ascii=False)}]}

        # --- mcp_howtocook_whatToEat ---
        elif tool_name == "mcp_howtocook_whatToEat":
            count = arguments.get("peopleCount", 2)
            return {"content": [{"type": "text", "text": _json.dumps({
                "peopleCount": count,
                "recommendations": [
                    "番茄炒蛋", "清炒时蔬", "可乐鸡翅",
                    "紫菜蛋花汤" if count <= 2 else "玉米排骨汤",
                ],
                "note": f"为{count}人推荐的菜品组合",
            }, ensure_ascii=False)}]}

        # --- mcp_howtocook_recommendMeals ---
        elif tool_name == "mcp_howtocook_recommendMeals":
            count = arguments.get("peopleCount", 2)
            allergies = arguments.get("allergies", [])
            avoid = arguments.get("avoidItems", [])
            return {"content": [{"type": "text", "text": _json.dumps({
                "peopleCount": count,
                "allergies": allergies,
                "avoidItems": avoid,
                "weeklyPlan": {
                    "周一": {"breakfast": "小米粥+鸡蛋", "lunch": "番茄炒蛋+米饭", "dinner": "清蒸鱼+蔬菜"},
                    "周二": {"breakfast": "全麦面包+牛奶", "lunch": "可乐鸡翅+米饭", "dinner": "蛋花汤+拌菜"},
                },
                "shoppingList": ["番茄", "鸡蛋", "鸡翅", "可乐", "大米", "蔬菜", "鱼"],
            }, ensure_ascii=False)}]}

        # --- mcp_howtocook_getAllRecipes ---
        elif tool_name == "mcp_howtocook_getAllRecipes":
            return {"content": [{"type": "text", "text": _json.dumps([
                {"name": "番茄炒蛋", "category": "素菜"},
                {"name": "可乐鸡翅", "category": "荤菜"},
                {"name": "红烧肉", "category": "荤菜"},
                {"name": "酸辣土豆丝", "category": "素菜"},
                {"name": "番茄蛋花汤", "category": "汤"},
            ], ensure_ascii=False)}]}

        return {"content": [{"type": "text", "text": _json.dumps({
            "error": f"Unknown tool: '{tool_name}'",
        }, ensure_ascii=False)}]}
