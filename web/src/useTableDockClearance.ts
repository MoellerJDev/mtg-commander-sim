import {
  type CSSProperties,
  type Dispatch,
  type SetStateAction,
  useEffect,
  useState,
} from "react";

type DockRef = Dispatch<SetStateAction<HTMLDivElement | null>>;

export function useTableDockClearance(): [DockRef, CSSProperties | undefined] {
  const [dock, setDock] = useState<HTMLDivElement | null>(null);
  const [clearance, setClearance] = useState(0);

  useEffect(() => {
    if (!dock) return undefined;
    const update = () => setClearance(
      Math.ceil(dock.getBoundingClientRect().height + 16),
    );
    update();
    const observer = new ResizeObserver(update);
    observer.observe(dock);
    return () => observer.disconnect();
  }, [dock]);

  const style = clearance > 0
    ? { "--table-dock-clearance": `${clearance}px` } as CSSProperties
    : undefined;
  return [setDock, style];
}
