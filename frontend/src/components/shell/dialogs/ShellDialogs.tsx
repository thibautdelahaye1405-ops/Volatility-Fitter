// The shell's modal dialogs (UI SHELL v2, S4), switched on the workbench's
// `dialog` slot: Universe manager, Options (settings), keyboard shortcuts,
// About. Each wraps an existing workspace view in the Dialog primitive.
import Dialog from "../Dialog";
import AboutDialog from "./AboutDialog";
import ShortcutsDialog from "./ShortcutsDialog";
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
        subtitle="Add or remove underlyings, choose each ticker's expiries, light / darken nodes, save named universes"
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
      <ShortcutsDialog open={dialog === "shortcuts"} onClose={closeDialog} />
      <AboutDialog open={dialog === "about"} onClose={closeDialog} />
    </>
  );
}
