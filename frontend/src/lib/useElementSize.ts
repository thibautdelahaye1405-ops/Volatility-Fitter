// Track the pixel size of a container element via ResizeObserver — the
// measurement hook behind the responsive hand-rolled SVG charts (SmileChart,
// the V3.4 weight strip). Extracted from SmileChart.tsx (file-size policy).
import { useLayoutEffect, useRef, useState } from "react";

/** Ref + live { width, height } of the referenced element's content box. */
export function useElementSize() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setSize({ width: rect.width, height: rect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, size };
}
