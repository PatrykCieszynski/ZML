export const IPC_NAMESPACE = "zml" as const;

export const IPC_CMD = {
    GET_BOOTSTRAP_STATE: `${IPC_NAMESPACE}:cmd:get_bootstrap_state`,
    GET_AGENT_HEALTH: `${IPC_NAMESPACE}:cmd:get_agent_health`,
} as const;

export const IPC_PUSH = {
    POSITION: `${IPC_NAMESPACE}:push:position`,
    STATE_PATCH: `${IPC_NAMESPACE}:push:state_patch`,
} as const;

export type IpcCmdChannel = (typeof IPC_CMD)[keyof typeof IPC_CMD];
export type IpcPushChannel = (typeof IPC_PUSH)[keyof typeof IPC_PUSH];
