export const IPC_NAMESPACE = "zml" as const;

export const IPC_CMD = {
    GET_BOOTSTRAP_STATE: `${IPC_NAMESPACE}:cmd:get_bootstrap_state`,
    GET_AGENT_HEALTH: `${IPC_NAMESPACE}:cmd:get_agent_health`,
    GET_OCR_CALIBRATION: `${IPC_NAMESPACE}:cmd:get_ocr_calibration`,
    RECALIBRATE_OCR: `${IPC_NAMESPACE}:cmd:recalibrate_ocr`,
    COPY_TEXT: `${IPC_NAMESPACE}:cmd:copy_text`,
    GET_ACTIVE_RUN: `${IPC_NAMESPACE}:cmd:get_active_run`,
    LIST_RUNS: `${IPC_NAMESPACE}:cmd:list_runs`,
    RESUME_RUN: `${IPC_NAMESPACE}:cmd:resume_run`,
    UPDATE_RUN: `${IPC_NAMESPACE}:cmd:update_run`,
    DELETE_RUN: `${IPC_NAMESPACE}:cmd:delete_run`,
    LIST_ACTIVE_RUN_SEGMENTS: `${IPC_NAMESPACE}:cmd:list_active_run_segments`,
    LIST_RUN_SEGMENTS: `${IPC_NAMESPACE}:cmd:list_run_segments`,
    UPDATE_RUN_SEGMENT_SETUP: `${IPC_NAMESPACE}:cmd:update_run_segment_setup`,
    SPLIT_RUN_SEGMENT: `${IPC_NAMESPACE}:cmd:split_run_segment`,
    MOVE_RUN_SEGMENT: `${IPC_NAMESPACE}:cmd:move_run_segment`,
    TOGGLE_MAP_WINDOW: `${IPC_NAMESPACE}:cmd:toggle_map_window`,
    TOGGLE_OVERLAY_WINDOW: `${IPC_NAMESPACE}:cmd:toggle_overlay_window`,
    START_RUN: `${IPC_NAMESPACE}:cmd:start_run`,
    STOP_RUN: `${IPC_NAMESPACE}:cmd:stop_run`,
    MARK_MINING_CLAIM_DEPLETED: `${IPC_NAMESPACE}:cmd:mark_mining_claim_depleted`,
    IGNORE_MINING_CLAIM: `${IPC_NAMESPACE}:cmd:ignore_mining_claim`,
    LIST_MINING_TOOLS: `${IPC_NAMESPACE}:cmd:list_mining_tools`,
    CREATE_MINING_TOOL: `${IPC_NAMESPACE}:cmd:create_mining_tool`,
    DELETE_MINING_TOOL: `${IPC_NAMESPACE}:cmd:delete_mining_tool`,
    GET_ACTIVE_MINING_TOOLS: `${IPC_NAMESPACE}:cmd:get_active_mining_tools`,
    SET_ACTIVE_MINING_TOOLS: `${IPC_NAMESPACE}:cmd:set_active_mining_tools`,
    CONNECT_CLOUD: `${IPC_NAMESPACE}:cmd:connect_cloud`,
    DISCONNECT_CLOUD: `${IPC_NAMESPACE}:cmd:disconnect_cloud`,
} as const;

export const IPC_PUSH = {
    POSITION: `${IPC_NAMESPACE}:push:position`,
    STATE_PATCH: `${IPC_NAMESPACE}:push:state_patch`,
} as const;

export type IpcCmdChannel = (typeof IPC_CMD)[keyof typeof IPC_CMD];
export type IpcPushChannel = (typeof IPC_PUSH)[keyof typeof IPC_PUSH];
