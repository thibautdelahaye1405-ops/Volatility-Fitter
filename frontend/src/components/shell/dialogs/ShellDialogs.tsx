// The shell's modal dialogs (UI SHELL v2, S4), switched on the workbench's
// `dialog` slot: Universe manager, Options (settings), the Help Center (with
// its Shortcuts page behind the legacy "shortcuts" id), About, and the Ctrl+P
// quick-open / Ctrl+K command palette (one component, ">" pre-filled for
// commands).
import Dialog from "../Dialog";
import AboutDialog from "./AboutDialog";
import HelpCenter from "../../help/HelpCenter";
import QuickOpen from "../QuickOpen";
import UniverseManager from "../../../views/UniverseManager";
import OptionsViewer from "../../../views/OptionsViewer";
import { useWorkbench } from "../../../state/workbench";

export default function ShellDialogs() {
  const { dialog, closeDialog } = useWorkbench();
  return (
    <>
      <Dialog
        open={dialog === "universe"}
        onClose={closeDialog}
        title="Manage universe"
        subtitle="Add or remove underlyings, choose each ticker's expiries, light / darken nodes, pick the data source, save named universes"
      >
        {dialog === "universe" && <UniverseManager />}
      </Dialog>
      <Dialog
        open={dialog === "options"}
        onClose={closeDialog}
        title="Options"
        subtitle="Calibration & model settings — Apply commits to the live backend; Save as default persists across restarts"
      >
        {dialog === "options" && <OptionsViewer />}
      </Dialog>
      {/* Help Center (HELP CENTER ARC) — "shortcuts" is the legacy id of its Shortcuts page. */}
      <HelpCenter open={dialog === "help" || dialog === "shortcuts"} onClose={closeDialog} />
      <AboutDialog open={dialog === "about"} onClose={closeDialog} />
      <QuickOpen
        open={dialog === "quickopen" || dialog === "commands"}
        initialQuery={dialog === "commands" ? ">" : ""}
        onClose={closeDialog}
      />
    </>
  );
}
