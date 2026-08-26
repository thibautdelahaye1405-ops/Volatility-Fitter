// View ▾ (UI SHELL v2, top-right): the display preferences — colour scheme,
// contrast / brightness, expiry-label format, live preview, Save as default /
// Reset — as an anchored popover. The content is the former View tab
// (ViewSettingsViewer), unchanged.
import { useState } from "react";
import { Eye } from "lucide-react";
import MenuButton from "./MenuButton";
import { MenuPanel } from "../../topbar/Menu";
import ViewSettingsViewer from "../../../views/ViewSettingsViewer";

export default function ViewMenu() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <MenuButton
        label="View"
        chevron
        active={open}
        title="Display preferences — colour scheme, contrast, expiry format"
        onClick={() => setOpen((v) => !v)}
      >
        <Eye size={13} strokeWidth={1.75} className="opacity-80" />
      </MenuButton>
      <MenuPanel open={open} onClose={() => setOpen(false)} align="right" width="w-[36rem]" scroll={false}>
        {/* The settings column scrolls itself (its Save bar sticks to its bottom). */}
        <div className="h-[min(78vh,46rem)]">
          <ViewSettingsViewer />
        </div>
      </MenuPanel>
    </div>
  );
}
