export const IPC_NAMESPACE = "zml" as const;

export const IPC_CMD = {
    GET_BOOTSTRAP_STATE: `${IPC_NAMESPACE}:cmd:get_bootstrap_state`,
} as const;

export const IPC_PUSH = {
    POSITION: `${IPC_NAMESPACE}:push:position`,
} as const;

export type IpcCmdChannel = (typeof IPC_CMD)[keyof typeof IPC_CMD];
export type IpcPushChannel = (typeof IPC_PUSH)[keyof typeof IPC_PUSH];
