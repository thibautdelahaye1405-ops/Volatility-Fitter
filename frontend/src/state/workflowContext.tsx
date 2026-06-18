// Shared workflow / data-source / as-of context.
//
// The TopBar (action buttons + source + as-of selectors) and the bottom
// StatusBar both need the live calibration/fetch status, the data-source lights
// and the as-of selection. Lifting these three hooks into one context means a
// single poll loop feeds both surfaces (no duplicate /calibration/status or
// /datasources polling) and the TopBar buttons and the StatusBar narrate the
// exact same state.
import { createContext, useCallback, useContext } from "react";
import type { ReactNode } from "react";
import { useSmileSession } from "./smileSession";
import { useWorkflow } from "./useWorkflow";
import type { UseWorkflowResult } from "./useWorkflow";
import { useDataSources } from "./useDataSources";
import type { UseDataSourcesResult } from "./useDataSources";
import { useAsOf } from "./useAsOf";
import type { UseAsOfResult } from "./useAsOf";

export interface WorkflowContextValue {
  /** True when a live backend is connected (vs mock data). */
  live: boolean;
  workflow: UseWorkflowResult;
  dataSources: UseDataSourcesResult;
  asof: UseAsOfResult;
}

const WorkflowContext = createContext<WorkflowContextValue | null>(null);

/** Mount inside SmileSessionProvider; provides the shared workflow state. */
export function WorkflowProvider({ children }: { children: ReactNode }) {
  const { source, refreshUniverse, reload, refreshViews, fitMode } = useSmileSession();
  const live = source === "live";

  // After a source / as-of switch, refetch the universe (keeps the selection
  // valid) and reload the current smile so every workspace reflects the change.
  const onSwitched = useCallback(() => {
    void refreshUniverse().then(reload).catch(reload);
  }, [refreshUniverse, reload]);

  const workflow = useWorkflow(live, refreshViews, fitMode);
  const dataSources = useDataSources(live, onSwitched);
  const asof = useAsOf(live, dataSources.active, onSwitched);

  return (
    <WorkflowContext.Provider value={{ live, workflow, dataSources, asof }}>
      {children}
    </WorkflowContext.Provider>
  );
}

/** Consume the shared workflow state; throws outside a WorkflowProvider. */
export function useWorkflowContext(): WorkflowContextValue {
  const ctx = useContext(WorkflowContext);
  if (ctx === null) {
    throw new Error("useWorkflowContext must be used within WorkflowProvider");
  }
  return ctx;
}
