import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { MainWindow as MainWindowBase } from "./mainWindowBase";
import { CalibrationView } from "./calibrationView";

export function MainWindow() {
  const [active, setActive] = useState(false);
  const [navHost, setNavHost] = useState<HTMLElement | null>(null);
  const [workspaceHost, setWorkspaceHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const resolveHosts = () => {
      if (cancelled) return;
      const nav = document.querySelector<HTMLElement>(".zml-nav");
      const workspace = document.querySelector<HTMLElement>(".zml-workspace");
      if (nav) setNavHost(nav);
      if (workspace) setWorkspaceHost(workspace);
      if (!nav || !workspace) requestAnimationFrame(resolveHosts);
    };
    resolveHosts();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!navHost) return;
    const handleNavigation = (event: Event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest(".zml-calibration-nav-item")) return;
      if (target.closest(".zml-nav-item")) setActive(false);
    };
    navHost.addEventListener("click", handleNavigation);
    return () => navHost.removeEventListener("click", handleNavigation);
  }, [navHost]);

  useEffect(() => {
    navHost?.classList.toggle("zml-calibration-active", active);
    workspaceHost?.classList.toggle("zml-calibration-active", active);
    return () => {
      navHost?.classList.remove("zml-calibration-active");
      workspaceHost?.classList.remove("zml-calibration-active");
    };
  }, [active, navHost, workspaceHost]);

  return (
    <>
      <MainWindowBase />
      {navHost && createPortal(
        <button
          type="button"
          className={active ? "zml-nav-item zml-calibration-nav-item is-active" : "zml-nav-item zml-calibration-nav-item"}
          onClick={() => setActive(true)}
        >
          Calibration
        </button>,
        navHost,
      )}
      {workspaceHost && active && createPortal(
        <div className="zml-calibration-host">
          <CalibrationView />
        </div>,
        workspaceHost,
      )}
    </>
  );
}
