export const IPC_NAMESPACE = "zml" as const;

export const IPC_CMD = {
    GET_BOOTSTRAP_STATE: `${IPC_NAMESPACE}:cmd:get_bootstrap_state`,
    GET_AGENT_HEALTH: `${IPC_NAMESPACE}:cmd:get_agent_health`,
    START_RUN: `${IPC_NAMESPACE}:cmd:start_run`,
    STOP_RUN: `${IPC_NAMESPACE}:cmd:stop_run`,
    LIST_MINING_TOOLS: `${IPC_NAMESPACE}:cmd:list_mining_tools`,
    CREATE_MINING_TOOL: `${IPC_NAMESPACE}:cmd:create_mining_tool`,
    DELETE_MINING_TOOL: `${IPC_NAMESPACE}:cmd:delete_mining_tool`,
    GET_ACTIVE_MINING_TOOLS: `${IPC_NAMESPACE}:cmd:get_active_mining_tools`,
    SET_ACTIVE_MINING_TOOLS: `${IPC_NAMESPACE}:cmd:set_active_mining_tools`,
} as const;

export const IPC_PUSH = {
    POSITION: `${IPC_NAMESPACE}:push:position`,
    STATE_PATCH: `${IPC_NAMESPACE}:push:state_patch`,
} as const;

export type IpcCmdChannel = (typeof IPC_CMD)[keyof typeof IPC_CMD];
export type IpcPushChannel = (typeof IPC_PUSH)[keyof typeof IPC_PUSH];
