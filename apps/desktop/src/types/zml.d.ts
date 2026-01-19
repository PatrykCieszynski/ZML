import type { BootstrapState, OcrPositionEvent, WindowType } from "@zml/shared";

declare global {
    interface Window {
        zml: {
            getBootstrapState: (windowType: WindowType) => Promise<BootstrapState>;
            onPosition: (cb: (event: OcrPositionEvent) => void) => () => void;
            offPosition: (cb: (event: OcrPositionEvent) => void) => void;
        };
    }
}

export {};
