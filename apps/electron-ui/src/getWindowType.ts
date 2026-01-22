import {isWindowType, WindowType} from "@zml/shared";


export function getWindowType(): WindowType {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get("windowType");

  // Developer ergonomics: if you open the Vite URL in a normal browser tab,
  // fall back to "main" rather than crashing instantly.
  if (raw == null) return "main";

  if (!isWindowType(raw)) return "main";
  return raw;
}
