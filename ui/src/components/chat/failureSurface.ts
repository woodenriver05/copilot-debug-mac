type ExtItem = {
  type: string;
  data?: any;
};

type SurfaceTone = "success" | "failure" | "neutral";

declare const __COPILOT_FAILURE_SURFACE_BUILD_ID__: string | undefined;

export const FAILURE_SURFACE_SCHEMA_VERSION = "run-pipeline-failure-surface-v2";
const FALLBACK_FAILURE_SURFACE_FORMATTER_BUILD_ID = "20260508-retrieval-fallback-v3";

function getFailureSurfaceFormatterBuildId(): string {
  if (
    typeof __COPILOT_FAILURE_SURFACE_BUILD_ID__ === "string" &&
    __COPILOT_FAILURE_SURFACE_BUILD_ID__.trim()
  ) {
    return __COPILOT_FAILURE_SURFACE_BUILD_ID__.trim();
  }
  return FALLBACK_FAILURE_SURFACE_FORMATTER_BUILD_ID;
}

export const FAILURE_SURFACE_FORMATTER_BUILD_ID = getFailureSurfaceFormatterBuildId();

export type DebugResultSurface = {
  title: string;
  tone: SurfaceTone;
  isWorkflowUpdate: boolean;
  isSuccessfulWorkflowUpdate: boolean;
  helpText: string | null;
  response: any;
};

export type RunPipelineFailureDebugSummary = {
  surface_schema_version: string;
  formatter_build_id: string;
  ext_type: string | null;
  source: string | null;
  execution_status: string | null;
  failed_stage: string;
  failure_reason: string;
  typed_failure_stage: string | null;
  typed_failure_reason: string | null;
  runtime_path_type: string | null;
  closure_blocker_reason: string | null;
  retrieval_fail_reason: string | null;
  dispatch_attempted: boolean | null;
  dispatch_status: string | null;
  prompt_id: string | null;
  image_paths_count: number;
  run_id: string | number | null;
  prediction_id: string | number | null;
};

const RUN_PIPELINE_FAILURE_EXT_TYPE = "run_pipeline_failure";
const RUN_PIPELINE_SUCCESS_STATUS = "success";

const FORBIDDEN_RECOVERY_TOKENS = [
  "apply_patch",
  "transfer_to_workflow_rewrite_agent",
  "generate_sketch.py",
  "rate_image",
];

export function getExtItems(response: any): ExtItem[] {
  return Array.isArray(response?.ext) ? response.ext : [];
}

export function findExtItem(response: any, type: string): ExtItem | undefined {
  return getExtItems(response).find((item) => item?.type === type);
}

export function hasGeneratedImageEvidence(data: any): boolean {
  return Boolean(data?.prompt_id) && Array.isArray(data?.image_paths) && data.image_paths.length > 0;
}

export function isFailedRunPipelineData(data: any): boolean {
  const executionStatus = data?.execution_status;
  const runtimeEvidence =
    data?.runtime_path_evidence && typeof data.runtime_path_evidence === "object" ? data.runtime_path_evidence : {};
  const hasFailureEvidence = Boolean(
    data?.failed_stage ||
      data?.failure_reason ||
      data?.typed_failure ||
      data?.retrieval_fail_reason ||
      data?.runtime_path_type ||
      data?.closure_blocker_reason ||
      runtimeEvidence.retrieval_fail_reason
  );
  return Boolean(
    data?.source === "run_pipeline" &&
      ((executionStatus && executionStatus !== RUN_PIPELINE_SUCCESS_STATUS) || hasFailureEvidence)
  );
}

export function isRunPipelineFailureExt(item: ExtItem | undefined): boolean {
  if (!item) {
    return false;
  }
  return item.type === RUN_PIPELINE_FAILURE_EXT_TYPE || isFailedRunPipelineData(item.data);
}

export function findRunPipelineFailureExt(response: any): ExtItem | undefined {
  return getExtItems(response).find(isRunPipelineFailureExt);
}

export function shouldApplyWorkflowUpdate(item: ExtItem | undefined): boolean {
  if (!item || item.type !== "workflow_update") {
    return false;
  }
  const data = item.data || {};
  if (data.source !== "run_pipeline") {
    return true;
  }
  if (data.execution_status === undefined || data.execution_status === null) {
    return true;
  }
  return data.execution_status === RUN_PIPELINE_SUCCESS_STATUS && hasGeneratedImageEvidence(data);
}

export function hasSuccessfulWorkflowUpdate(response: any): boolean {
  return shouldApplyWorkflowUpdate(findExtItem(response, "workflow_update"));
}

export function hasForbiddenRecoveryText(text: string): boolean {
  return FORBIDDEN_RECOVERY_TOKENS.some((token) => text.includes(token));
}

function getStageFromRuntimePathType(runtimePathType: string | null | undefined): string | null {
  if (runtimePathType === "no_execution_ready_fail_closed") {
    return "search";
  }
  if (runtimePathType === "fallback_composer_skeleton") {
    return "composer";
  }
  if (runtimePathType === "direct_prompt_bypass") {
    return "router";
  }
  return null;
}

function getStageFromRetrievalFailReason(retrievalFailReason: string | null | undefined): string | null {
  if (retrievalFailReason === "no_execution_ready_workflow") {
    return "search";
  }
  return null;
}

function getRunPipelineFailureData(responseOrData: any): { extType: string | null; data: any } | null {
  const failureExt = findRunPipelineFailureExt(responseOrData);
  if (failureExt) {
    return {
      extType: failureExt.type || null,
      data: failureExt.data || {},
    };
  }
  if (
    isFailedRunPipelineData(responseOrData) ||
    responseOrData?.typed_failure ||
    responseOrData?.failed_stage ||
    responseOrData?.failure_reason ||
    responseOrData?.retrieval_fail_reason ||
    responseOrData?.runtime_path_type ||
    responseOrData?.closure_blocker_reason ||
    (responseOrData?.runtime_path_evidence &&
      typeof responseOrData.runtime_path_evidence === "object" &&
      responseOrData.runtime_path_evidence.retrieval_fail_reason)
  ) {
    return {
      extType: null,
      data: responseOrData || {},
    };
  }
  return null;
}

export function getRunPipelineFailureDebugSummary(responseOrData: any): RunPipelineFailureDebugSummary | null {
  const failureData = getRunPipelineFailureData(responseOrData);
  if (!failureData) {
    return null;
  }

  const data = failureData.data;
  const imagePaths = Array.isArray(data?.image_paths) ? data.image_paths : [];
  const typedFailure = data?.typed_failure && typeof data.typed_failure === "object" ? data.typed_failure : {};
  const runtimeEvidence =
    data?.runtime_path_evidence && typeof data.runtime_path_evidence === "object" ? data.runtime_path_evidence : {};
  const stageFromRuntimePath = getStageFromRuntimePathType(data?.runtime_path_type);
  const topLevelRetrievalFailReason = data?.retrieval_fail_reason ?? null;
  const runtimeRetrievalFailReason = runtimeEvidence.retrieval_fail_reason ?? null;
  const retrievalFailReason = topLevelRetrievalFailReason ?? runtimeRetrievalFailReason;
  const stageFromRetrievalFailReason = getStageFromRetrievalFailReason(retrievalFailReason);
  const failedStage =
    data?.failed_stage || typedFailure.stage || stageFromRuntimePath || stageFromRetrievalFailReason || "unknown";
  const failureReason =
    data?.failure_reason ||
    typedFailure.failure_reason ||
    typedFailure.typed_reason ||
    data?.closure_blocker_reason ||
    retrievalFailReason ||
    "unknown";

  return {
    surface_schema_version: FAILURE_SURFACE_SCHEMA_VERSION,
    formatter_build_id: FAILURE_SURFACE_FORMATTER_BUILD_ID,
    ext_type: failureData.extType,
    source: data?.source ?? null,
    execution_status: data?.execution_status ?? null,
    failed_stage: failedStage,
    failure_reason: failureReason,
    typed_failure_stage: typedFailure.stage ?? null,
    typed_failure_reason: typedFailure.failure_reason ?? typedFailure.typed_reason ?? null,
    runtime_path_type: data?.runtime_path_type ?? null,
    closure_blocker_reason: data?.closure_blocker_reason ?? null,
    retrieval_fail_reason: retrievalFailReason,
    dispatch_attempted: data?.dispatch_attempted ?? null,
    dispatch_status: data?.dispatch_status ?? null,
    prompt_id: data?.prompt_id ?? null,
    image_paths_count: imagePaths.length,
    run_id: data?.run_id ?? null,
    prediction_id: data?.prediction_id ?? null,
  };
}

export function buildRunPipelineFailureMarkdown(data: any): string {
  const summary = getRunPipelineFailureDebugSummary(data);
  const runId = data?.run_id ?? data?.prediction_id ?? null;
  const promptId = data?.prompt_id ?? null;
  const imagePaths = Array.isArray(data?.image_paths) ? data.image_paths : [];
  const lines = [
    "### Run Failed Before Image Generation",
    "",
    `- execution_status: \`${data?.execution_status || "failed"}\``,
    `- failed_stage: \`${summary?.failed_stage || "unknown"}\``,
    `- failure_reason: \`${summary?.failure_reason || "unknown"}\``,
    `- surface_schema_version: \`${FAILURE_SURFACE_SCHEMA_VERSION}\``,
    `- formatter_build_id: \`${FAILURE_SURFACE_FORMATTER_BUILD_ID}\``,
  ];

  if (data?.dispatch_attempted !== undefined && data?.dispatch_attempted !== null) {
    lines.push(`- dispatch_attempted: \`${data.dispatch_attempted}\``);
  }
  if (data?.dispatch_status !== undefined && data?.dispatch_status !== null) {
    lines.push(`- dispatch_status: \`${data.dispatch_status}\``);
  }
  if (data?.runtime_path_type !== undefined && data?.runtime_path_type !== null) {
    lines.push(`- runtime_path_type: \`${data.runtime_path_type}\``);
  }
  if (data?.closure_eligible !== undefined && data?.closure_eligible !== null) {
    lines.push(`- closure_eligible: \`${data.closure_eligible}\``);
  }
  if (data?.closure_blocker_reason !== undefined && data?.closure_blocker_reason !== null) {
    lines.push(`- closure_blocker_reason: \`${data.closure_blocker_reason}\``);
  }
  if (summary?.retrieval_fail_reason !== undefined && summary?.retrieval_fail_reason !== null) {
    lines.push(`- retrieval_fail_reason: \`${summary.retrieval_fail_reason}\``);
  }

  lines.push(`- prompt_id: \`${promptId}\``);
  lines.push(`- image_paths: \`${imagePaths.length}\``);

  if (runId !== null && runId !== undefined) {
    lines.push(`- run_id: \`${runId}\` (failed run evidence, not a generated image ID)`);
  }

  lines.push("");
  lines.push("No image was created for this run. Image rating and image-based recovery actions are unavailable.");
  return lines.join("\n");
}

export function getDebugResultSurface(response: any): DebugResultSurface {
  const failureExt = findRunPipelineFailureExt(response);
  if (failureExt) {
    return {
      title: "Run Failed Before Image Generation",
      tone: "failure",
      isWorkflowUpdate: false,
      isSuccessfulWorkflowUpdate: false,
      helpText: null,
      response: {
        ...(response || {}),
        text: buildRunPipelineFailureMarkdown(failureExt.data || {}),
      },
    };
  }

  const successfulWorkflowUpdate = hasSuccessfulWorkflowUpdate(response);
  if (successfulWorkflowUpdate) {
    return {
      title: "Workflow Updated Successfully",
      tone: "success",
      isWorkflowUpdate: true,
      isSuccessfulWorkflowUpdate: true,
      helpText: "If you're not satisfied with the changes, click the restore button to revert to the previous version.",
      response,
    };
  }

  const workflowUpdateExt = findExtItem(response, "workflow_update");
  if (workflowUpdateExt) {
    return {
      title: "Workflow Update Not Applied",
      tone: "neutral",
      isWorkflowUpdate: false,
      isSuccessfulWorkflowUpdate: false,
      helpText: null,
      response,
    };
  }

  return {
    title: "Workflow Updated Finished",
    tone: "neutral",
    isWorkflowUpdate: false,
    isSuccessfulWorkflowUpdate: false,
    helpText: null,
    response,
  };
}
