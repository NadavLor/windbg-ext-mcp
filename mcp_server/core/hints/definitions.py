"""
Complete tool definitions and metadata for WinDbg MCP tools.

This module contains all the tool definitions with their parameters, actions,
examples, and validation rules. It's separated from the main validator logic
for better maintainability.
"""
from typing import Dict
from .data_structures import ParameterInfo, ActionInfo, ToolInfo

def get_tool_definitions() -> Dict[str, ToolInfo]:
    """Initialize complete tool definitions with parameters and hints."""
    tools = {}
    
    # debug_session tool
    tools["debug_session"] = ToolInfo(
        name="debug_session",
        description="Manage and get information about the debugging session",
        actions={
            "status": ActionInfo(
                name="status",
                description="Get current debugging session status and metadata",
                parameters=[],
                examples=[
                    "debug_session(action='status')",
                    "debug_session()  # status is default"
                ]
            ),
            "connection": ActionInfo(
                name="connection",
                description="Test connection to WinDbg extension",
                parameters=[],
                examples=["debug_session(action='connection')"]
            ),
            "metadata": ActionInfo(
                name="metadata",
                description="Get detailed session metadata including version and modules",
                parameters=[],
                examples=["debug_session(action='metadata')"]
            ),
            "version": ActionInfo(
                name="version",
                description="Get WinDbg version information",
                parameters=[],
                examples=["debug_session(action='version')"]
            )
        },
        common_workflows=[
            "Start with debug_session(action='connection') to verify connectivity",
            "Use debug_session(action='status') to check debugging mode (kernel/user)",
            "Get version info with debug_session(action='version')"
        ]
    )
    
    # run_command tool
    tools["run_command"] = ToolInfo(
        name="run_command",
        description="Execute WinDbg commands directly",
        actions={
            "": ActionInfo(  # No specific action, just parameters
                name="execute",
                description="Execute a WinDbg command",
                parameters=[
                    ParameterInfo(
                        name="command",
                        type="string",
                        required=True,
                        description="WinDbg command to execute",
                        examples=[
                            "command='lm'  # List modules",
                            "command='k'   # Stack trace", 
                            "command='r'   # Registers",
                            "command='!process 0 0'  # List processes",
                            "command='dd 0x1000'  # Display memory"
                        ]
                    ),
                    ParameterInfo(
                        name="validate",
                        type="boolean",
                        required=False,
                        description="Whether to validate command for safety",
                        examples=["validate=True  # Default", "validate=False  # Skip validation"],
                        default_value=True
                    )
                ],
                                examples=[                    "run_command(action='', command='lm')",                    "run_command(action='', command='k', validate=False)",                    "run_command(command='lm')  # action defaults to ''",                    "run_command(command='!process 0 0')"                ]
            )
        },
        common_workflows=[
            "Use for direct WinDbg commands when specific tools don't cover your needs",
            "Good for one-off commands or testing",
            "Consider using specialized tools (analyze_*) for better error handling"
        ]
    )
    
    # analyze_process tool
    tools["analyze_process"] = ToolInfo(
        name="analyze_process",
        description="Analyze processes in the debugging session",
        actions={
            "list": ActionInfo(
                name="list",
                description="List all processes in the debugging session",
                parameters=[],
                examples=["analyze_process(action='list')"],
                next_steps=[
                    "Copy process address from output for other actions",
                    "Use analyze_process(action='info', address='...') for details",
                    "Switch context with analyze_process(action='switch', address='...')"
                ]
            ),
            "switch": ActionInfo(
                name="switch",
                description="Switch to a specific process context",
                parameters=[
                    ParameterInfo(
                        name="address",
                        type="string",
                        required=True,
                        description="Process address (from list action)",
                        examples=[
                            "address='0xffff8e0e481d7080'",
                            "address='ffffc001e1234567'"
                        ],
                        validation_pattern=r'^(0x)?[a-fA-F0-9`]+$'
                    ),
                    ParameterInfo(
                        name="save_context",
                        type="boolean",
                        required=False,
                        description="Save current context for later restore",
                        examples=["save_context=True  # Default", "save_context=False"],
                        default_value=True
                    )
                ],
                examples=[
                    "analyze_process(action='switch', address='0xffff8e0e481d7080')",
                    "analyze_process(action='switch', address='ffffc001e1234567', save_context=False)"
                ],
                next_steps=[
                    "After switching, use analyze_thread(action='list') to see threads",
                    "Use analyze_memory tools to examine process memory",
                    "Use analyze_process(action='restore') to return to previous context"
                ]
            ),
            "info": ActionInfo(
                name="info",
                description="Get detailed information about a specific process",
                parameters=[
                    ParameterInfo(
                        name="address",
                        type="string",
                        required=True,
                        description="Process address (from list action)",
                        examples=[
                            "address='0xffff8e0e481d7080'",
                            "address='ffffc001e1234567'"
                        ],
                        validation_pattern=r'^(0x)?[a-fA-F0-9`]+$'
                    )
                ],
                examples=["analyze_process(action='info', address='0xffff8e0e481d7080')"]
            ),
            "peb": ActionInfo(
                name="peb",
                description="Get Process Environment Block information",
                parameters=[
                    ParameterInfo(
                        name="address",
                        type="string",
                        required=False,
                        description="Process address (uses current process if not specified)",
                        examples=[
                            "address='0xffff8e0e481d7080'  # Specific process",
                            "# No address = current process"
                        ],
                        validation_pattern=r'^(0x)?[a-fA-F0-9`]+$'
                    )
                ],
                examples=[
                    "analyze_process(action='peb')  # Current process",
                    "analyze_process(action='peb', address='0xffff8e0e481d7080')"
                ],
                user_mode_only=True  # PEB is user-mode concept
            ),
            "restore": ActionInfo(
                name="restore",
                description="Restore previously saved process context",
                parameters=[],
                examples=["analyze_process(action='restore')"]
            )
        },
        common_workflows=[
            "1. List processes with action='list'",
            "2. Switch to target process with action='switch'",
            "3. Perform analysis (threads, memory, etc.)",
            "4. Restore context with action='restore'"
        ]
    )
    
    # analyze_thread tool
    tools["analyze_thread"] = ToolInfo(
        name="analyze_thread",
        description="Analyze threads in the debugging session",
        actions={
            "list": ActionInfo(
                name="list",
                description="List all threads in current process",
                parameters=[],
                examples=["analyze_thread(action='list')"],
                next_steps=[
                    "Copy thread ID from output for other actions",
                    "Switch to specific thread with analyze_thread(action='switch', thread_id='...')",
                    "Get thread details with analyze_thread(action='info', thread_id='...')"
                ]
            ),
            "switch": ActionInfo(
                name="switch",
                description="Switch to a specific thread context",
                parameters=[
                    ParameterInfo(
                        name="thread_id",
                        type="string",
                        required=True,
                        description="Thread ID (from list action)",
                        examples=[
                            "thread_id='0'",
                            "thread_id='4'"
                        ],
                        validation_pattern=r'^\d+$'
                    )
                ],
                examples=["analyze_thread(action='switch', thread_id='0')"]
            ),
            "info": ActionInfo(
                name="info",
                description="Get detailed information about a specific thread",
                parameters=[
                    ParameterInfo(
                        name="thread_id",
                        type="string",
                        required=False,
                        description="Thread ID (uses current thread if not specified)",
                        examples=[
                            "thread_id='0'  # Specific thread",
                            "# No thread_id = current thread"
                        ],
                        validation_pattern=r'^\d+$'
                    )
                ],
                examples=[
                    "analyze_thread(action='info')  # Current thread",
                    "analyze_thread(action='info', thread_id='0')"
                ]
            ),
            "stack": ActionInfo(
                name="stack",
                description="Get stack trace for a thread",
                parameters=[
                    ParameterInfo(
                        name="thread_id",
                        type="string",
                        required=False,
                        description="Thread ID (uses current thread if not specified)",
                        examples=[
                            "thread_id='0'  # Specific thread",
                            "# No thread_id = current thread"
                        ],
                        validation_pattern=r'^\d+$'
                    ),
                    ParameterInfo(
                        name="detailed",
                        type="boolean",
                        required=False,
                        description="Include detailed stack information",
                        examples=["detailed=True", "detailed=False  # Default"],
                        default_value=False
                    )
                ],
                examples=[
                    "analyze_thread(action='stack')",
                    "analyze_thread(action='stack', thread_id='0', detailed=True)"
                ]
            )
        },
        common_workflows=[
            "1. List threads with action='list'",
            "2. Switch to target thread with action='switch'",
            "3. Examine stack with action='stack'",
            "4. Get detailed info with action='info'"
        ]
    )
    
    # analyze_memory tool
    tools["analyze_memory"] = ToolInfo(
        name="analyze_memory",
        description="Analyze memory and data structures",
        actions={
            "display": ActionInfo(
                name="display",
                description="Display memory at specified address",
                parameters=[
                    ParameterInfo(
                        name="address",
                        type="string",
                        required=True,
                        description="Memory address to display",
                        examples=[
                            "address='0x1000'",
                            "address='fffff805`51400000'"
                        ],
                        validation_pattern=r'^(0x)?[a-fA-F0-9`]+$'
                    ),
                    ParameterInfo(
                        name="length",
                        type="integer",
                        required=False,
                        description="Number of bytes to display (default: 32)",
                        examples=[
                            "length=32  # Default",
                            "length=64"
                        ],
                        default_value=32
                    )
                ],
                examples=[
                    "analyze_memory(action='display', address='0x1000')",
                    "analyze_memory(action='display', address='fffff805`51400000', length=64)"
                ]
            ),
            "type": ActionInfo(
                name="type",
                description="Display memory as a specific data type/structure",
                parameters=[
                    ParameterInfo(
                        name="address",
                        type="string",
                        required=True,
                        description="Memory address of the structure",
                        examples=[
                            "address='0x1000'",
                            "address='fffff805`51400000'"
                        ],
                        validation_pattern=r'^(0x)?[a-fA-F0-9`]+$'
                    ),
                    ParameterInfo(
                        name="type_name",
                        type="string",
                        required=True,
                        description="Type/structure name to interpret as",
                        examples=[
                            "type_name='_EPROCESS'",
                            "type_name='_KTHREAD'"
                        ]
                    )
                ],
                examples=[
                    "analyze_memory(action='type', address='0x1000', type_name='_EPROCESS')",
                    "analyze_memory(action='type', address='fffff805`51400000', type_name='_KTHREAD')"
                ]
            ),
            "search": ActionInfo(
                name="search",
                description="Search for patterns in memory",
                parameters=[
                    ParameterInfo(
                        name="address",
                        type="string",
                        required=True,
                        description="Pattern to search for (as address parameter)",
                        examples=[
                            "address='4d 5a'  # PE header",
                            "address='kernel32.dll'"
                        ]
                    )
                ],
                examples=[
                    "analyze_memory(action='search', address='4d 5a')",
                    "analyze_memory(action='search', address='kernel32.dll')"
                ]
            ),
            "pte": ActionInfo(
                name="pte",
                description="Display Page Table Entry information for an address",
                parameters=[
                    ParameterInfo(
                        name="address",
                        type="string",
                        required=True,
                        description="Virtual address to examine PTE for",
                        examples=[
                            "address='0x1000'",
                            "address='fffff805`51400000'"
                        ],
                        validation_pattern=r'^(0x)?[a-fA-F0-9`]+$'
                    )
                ],
                examples=[
                    "analyze_memory(action='pte', address='0x1000')",
                    "analyze_memory(action='pte', address='fffff805`51400000')"
                ]
            ),
            "regions": ActionInfo(
                name="regions",
                description="Display memory regions and their properties",
                parameters=[],
                examples=[
                    "analyze_memory(action='regions')"
                ]
            )
        },
        common_workflows=[
            "1. Display memory with action='display'",
            "2. Interpret structures with action='type'", 
            "3. Search for patterns with action='search'",
            "4. Check page table entries with action='pte'",
            "5. View memory layout with action='regions'"
        ]
    )
    
    return tools 