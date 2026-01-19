import type { BootstrapState, OcrPositionEvent, WindowType } from "@zml/shared";

export {};

declare global {
    type ZmlApi = {
        ping(): string;

        getBootstrapState(windowType: WindowType): Promise<BootstrapState>;

        onPosition(cb: (event: OcrPositionEvent) => void): () => void;
    };

    interface Window {
        zml?: ZmlApi;
    }
}
