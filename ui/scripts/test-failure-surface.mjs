import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import ts from "typescript";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const helperPath = path.resolve(scriptDir, "../src/components/chat/failureSurface.ts");
const fixturePath = path.resolve(scriptDir, "../../backend/tests/fixtures/failure_surface_cases.json");
const source = fs.readFileSync(helperPath, "utf8");
const fixtureCases = JSON.parse(fs.readFileSync(fixturePath, "utf8")).cases;
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;

const exportsObject = {};
const sandbox = {
  exports: exportsObject,
  module: { exports: exportsObject },
};
vm.runInNewContext(compiled, sandbox, { filename: helperPath });

const helpers = sandbox.module.exports;
assert.equal(helpers.FAILURE_SURFACE_FORMATTER_BUILD_ID, "20260508-surface-decision-v4");

const injectedBuildExportsObject = {};
const injectedBuildSandbox = {
  exports: injectedBuildExportsObject,
  module: { exports: injectedBuildExportsObject },
  __COPILOT_FAILURE_SURFACE_BUILD_ID__: "test-build-id",
};
vm.runInNewContext(compiled, injectedBuildSandbox, { filename: helperPath });
assert.equal(injectedBuildSandbox.module.exports.FAILURE_SURFACE_FORMATTER_BUILD_ID, "test-build-id");

const storageHelperPath = path.resolve(scriptDir, "../src/utils/failureSurfaceStorageDebug.ts");
const storageSource = fs.readFileSync(storageHelperPath, "utf8");
const storageCompiled = ts.transpileModule(storageSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const storageExportsObject = {};
const storageSandbox = {
  exports: storageExportsObject,
  module: { exports: storageExportsObject },
  require: (specifier) => {
    if (specifier === "../components/chat/failureSurface") {
      return helpers;
    }
    if (specifier === "../types/types") {
      return {};
    }
    throw new Error(`Unexpected require in storage helper test: ${specifier}`);
  },
};
vm.runInNewContext(storageCompiled, storageSandbox, { filename: storageHelperPath });
const storageHelpers = storageSandbox.module.exports;
assert.equal(storageHelpers.FAILURE_SURFACE_CACHE_SCHEMA_VERSION, "copilot-message-cache-v3");

const failedData = {
  source: "run_pipeline",
  execution_status: "failed",
  failed_stage: "planner",
  failure_reason: "invalid_choice_retry_suppressed",
  dispatch_attempted: false,
  dispatch_status: null,
  prompt_id: null,
  image_paths: [],
  prediction_id: 60,
  run_id: 60,
};

const failedWorkflowUpdate = {
  type: "workflow_update",
  data: {
    ...failedData,
    workflow_data: { nodes: [] },
  },
};

const failedWorkflowResponse = {
  text: "apply_patch transfer_to_workflow_rewrite_agent generate_sketch.py rate_image",
  ext: [failedWorkflowUpdate],
};

assert.equal(
  helpers.shouldApplyWorkflowUpdate(failedWorkflowUpdate),
  false,
  "failed run_pipeline workflow_update must not apply to canvas",
);

const failedSurface = helpers.getDebugResultSurface(failedWorkflowResponse);
assert.equal(failedSurface.title, "Run Failed Before Image Generation");
assert.equal(failedSurface.tone, "failure");
assert.equal(failedSurface.isSuccessfulWorkflowUpdate, false);
assert.match(failedSurface.response.text, /run_id: `60` \(failed run evidence/);
assert.doesNotMatch(failedSurface.response.text, /apply_patch/);
assert.doesNotMatch(failedSurface.response.text, /transfer_to_workflow_rewrite_agent/);
assert.doesNotMatch(failedSurface.response.text, /generate_sketch\.py/);
assert.doesNotMatch(failedSurface.response.text, /rate_image/);
assert.doesNotMatch(failedSurface.response.text, /image generation succeeded/i);

const typedFailureSurface = helpers.getDebugResultSurface({
  text: "generate_sketch.py --output fake.png",
  ext: [{ type: "run_pipeline_failure", data: failedData }],
});
assert.equal(typedFailureSurface.tone, "failure");
assert.doesNotMatch(typedFailureSurface.response.text, /generate_sketch\.py/);

const typedFailureOnlySurface = helpers.getDebugResultSurface({
  text: "no image",
  ext: [
    {
      type: "run_pipeline_failure",
      data: {
        source: "run_pipeline",
        execution_status: "failed",
        typed_failure: {
          stage: "search",
          typed_reason: "no_execution_ready_workflow",
          failure_reason: "no_execution_ready_workflow",
        },
        dispatch_attempted: false,
        dispatch_status: "not_attempted",
        prompt_id: null,
        image_paths: [],
        run_id: 148,
      },
    },
  ],
});
assert.match(typedFailureOnlySurface.response.text, /failed_stage: `search`/);
assert.match(typedFailureOnlySurface.response.text, /failure_reason: `no_execution_ready_workflow`/);
assert.match(typedFailureOnlySurface.response.text, /surface_schema_version: `run-pipeline-failure-surface-v2`/);
assert.match(typedFailureOnlySurface.response.text, /formatter_build_id: `20260508-surface-decision-v4`/);
assert.doesNotMatch(typedFailureOnlySurface.response.text, /unknown/);

const typedFailureSummary = helpers.getRunPipelineFailureDebugSummary({
  text: "no image",
  ext: [
    {
      type: "run_pipeline_failure",
      data: {
        source: "run_pipeline",
        execution_status: "failed",
        typed_failure: {
          stage: "search",
          typed_reason: "no_execution_ready_workflow",
          failure_reason: "no_execution_ready_workflow",
        },
        dispatch_attempted: false,
        dispatch_status: "not_attempted",
        prompt_id: null,
        image_paths: [],
        run_id: 148,
      },
    },
  ],
});
assert.equal(typedFailureSummary.failed_stage, "search");
assert.equal(typedFailureSummary.failure_reason, "no_execution_ready_workflow");
assert.equal(typedFailureSummary.surface_schema_version, "run-pipeline-failure-surface-v2");
assert.equal(typedFailureSummary.formatter_build_id, "20260508-surface-decision-v4");

const runtimePathOnlySurface = helpers.getDebugResultSurface({
  text: "no image",
  ext: [
    {
      type: "run_pipeline_failure",
      data: {
        source: "run_pipeline",
        execution_status: "skipped",
        runtime_path_type: "no_execution_ready_fail_closed",
        closure_eligible: false,
        closure_blocker_reason: "no_execution_ready_workflow",
        runtime_path_evidence: {
          retrieval_fail_reason: "no_execution_ready_workflow",
        },
        dispatch_attempted: false,
        dispatch_status: "not_applicable",
        prompt_id: null,
        image_paths: [],
      },
    },
  ],
});
assert.match(runtimePathOnlySurface.response.text, /failed_stage: `search`/);
assert.match(runtimePathOnlySurface.response.text, /failure_reason: `no_execution_ready_workflow`/);
assert.match(runtimePathOnlySurface.response.text, /runtime_path_type: `no_execution_ready_fail_closed`/);
assert.match(runtimePathOnlySurface.response.text, /closure_blocker_reason: `no_execution_ready_workflow`/);
assert.match(runtimePathOnlySurface.response.text, /retrieval_fail_reason: `no_execution_ready_workflow`/);
assert.doesNotMatch(runtimePathOnlySurface.response.text, /unknown/);

const topLevelRetrievalOnlySurface = helpers.getDebugResultSurface({
  text: "no image",
  ext: [
    {
      type: "run_pipeline_failure",
      data: {
        source: "run_pipeline",
        execution_status: "skipped",
        retrieval_fail_reason: "no_execution_ready_workflow",
        dispatch_attempted: false,
        dispatch_status: "not_applicable",
        prompt_id: null,
        image_paths: [],
        run_id: "run-skipped",
      },
    },
  ],
});
assert.match(topLevelRetrievalOnlySurface.response.text, /failed_stage: `search`/);
assert.match(topLevelRetrievalOnlySurface.response.text, /failure_reason: `no_execution_ready_workflow`/);
assert.match(topLevelRetrievalOnlySurface.response.text, /retrieval_fail_reason: `no_execution_ready_workflow`/);
assert.doesNotMatch(topLevelRetrievalOnlySurface.response.text, /unknown/);

for (const fixtureCase of fixtureCases) {
  const expected = fixtureCase.expected;
  const extType =
    expected.selected_surface === "workflow_update"
      ? "workflow_update"
      : expected.selected_surface === "surface_contract_violation"
        ? "run_pipeline_surface_contract_violation"
        : "run_pipeline_failure";
  const response = {
    text: "no image",
    ext: [{ type: extType, data: fixtureCase.data }],
  };
  const summary = helpers.getRunPipelineFailureDebugSummary(response);
  const surface = helpers.getDebugResultSurface(response);
  const decision = helpers.getRunPipelineSurfaceDecision(fixtureCase.data);

  assert.equal(decision.selected_surface, expected.selected_surface, fixtureCase.name);
  if (expected.matched_success_predicates) {
    assert.equal(
      JSON.stringify(decision.matched_success_predicates),
      JSON.stringify(expected.matched_success_predicates),
      fixtureCase.name,
    );
  }
  if (expected.matched_failure_predicates) {
    assert.equal(
      JSON.stringify(decision.matched_failure_predicates),
      JSON.stringify(expected.matched_failure_predicates),
      fixtureCase.name,
    );
  }

  if (expected.selected_surface === "run_pipeline_failure") {
    assert.equal(summary.failed_stage, expected.failed_stage, fixtureCase.name);
    assert.equal(summary.failure_reason, expected.failure_reason, fixtureCase.name);
    assert.equal(summary.retrieval_fail_reason, expected.retrieval_fail_reason, fixtureCase.name);
    assert.ok(surface.response.text.includes(`failed_stage: \`${expected.failed_stage}\``), fixtureCase.name);
    assert.ok(surface.response.text.includes(`failure_reason: \`${expected.failure_reason}\``), fixtureCase.name);
    if (expected.retrieval_fail_reason !== null) {
      assert.ok(
        surface.response.text.includes(`retrieval_fail_reason: \`${expected.retrieval_fail_reason}\``),
        fixtureCase.name,
      );
    }
    if (expected.detects_direct_data) {
      assert.notEqual(helpers.getRunPipelineFailureDebugSummary(fixtureCase.data), null, fixtureCase.name);
    }
    if (expected.no_unknown) {
      assert.doesNotMatch(surface.response.text, /unknown/, fixtureCase.name);
    }
  }

  if (expected.selected_surface === "workflow_update") {
    assert.equal(summary, null, fixtureCase.name);
    assert.equal(surface.title, "Workflow Updated Successfully", fixtureCase.name);
    assert.equal(surface.isSuccessfulWorkflowUpdate, true, fixtureCase.name);
    assert.equal(helpers.isFailedRunPipelineData(fixtureCase.data), false, fixtureCase.name);
    assert.equal(helpers.findRunPipelineFailureExt(response), undefined, fixtureCase.name);
  }

  if (expected.selected_surface === "surface_contract_violation") {
    assert.notEqual(helpers.findRunPipelineSurfaceContractViolationExt(response), undefined, fixtureCase.name);
    assert.equal(surface.title, "Surface Contract Violation", fixtureCase.name);
    assert.match(surface.response.text, /failed_stage: `response_surface_adapter`/, fixtureCase.name);
    assert.match(surface.response.text, /failure_reason: `surface_classifier_contradiction`/, fixtureCase.name);
    assert.doesNotMatch(surface.response.text, /Run Failed Before Image Generation/, fixtureCase.name);
  }
}

const contractViolationFixture = fixtureCases.find(
  (fixtureCase) => fixtureCase.name === "success_with_failure_reason_becomes_contract_violation",
);
assert.ok(contractViolationFixture);
const workflowUpdateWithContractViolation = {
  text: "contradictory run_pipeline result",
  ext: [
    {
      type: "workflow_update",
      data: {
        source: "run_pipeline",
        execution_status: "success",
        prompt_id: contractViolationFixture.data.prompt_id,
        image_paths: contractViolationFixture.data.image_paths,
        workflow_data: contractViolationFixture.data.selected_workflow,
      },
    },
    {
      type: "run_pipeline_surface_contract_violation",
      data: contractViolationFixture.data,
    },
  ],
};
assert.equal(helpers.shouldApplyWorkflowUpdate(workflowUpdateWithContractViolation.ext[0]), true);
assert.equal(
  helpers.shouldApplyWorkflowUpdateForResponse(
    workflowUpdateWithContractViolation,
    workflowUpdateWithContractViolation.ext[0],
  ),
  false,
);
assert.equal(helpers.hasSuccessfulWorkflowUpdate(workflowUpdateWithContractViolation), false);
assert.equal(helpers.getDebugResultSurface(workflowUpdateWithContractViolation).title, "Surface Contract Violation");

const successWorkflowUpdate = {
  type: "workflow_update",
  data: {
    source: "run_pipeline",
    execution_status: "success",
    trace_id: "trace-ok",
    dispatch_attempted: true,
    dispatch_status: "succeeded",
    runtime_path_type: "canonical_selected_template",
    prompt_id: "prompt-123",
    image_paths: ["output/red-bicycle.png"],
    prediction_id: 61,
    workflow_data: { nodes: [] },
  },
};
const successSurface = helpers.getDebugResultSurface({
  text: "ok",
  ext: [successWorkflowUpdate],
});
assert.equal(helpers.shouldApplyWorkflowUpdate(successWorkflowUpdate), true);
assert.equal(successSurface.title, "Workflow Updated Successfully");
assert.equal(successSurface.tone, "success");
assert.equal(successSurface.isSuccessfulWorkflowUpdate, true);
assert.equal(helpers.isFailedRunPipelineData(successWorkflowUpdate.data), false);

const cachedRawFailureMessages = storageHelpers.sanitizeFailureSurfaceCacheMessages([
  {
    id: "cached-raw",
    role: "ai",
    content: JSON.stringify({
      text: "old formatter text",
      finished: true,
      format: "markdown",
      ext: [
        {
          type: "run_pipeline_failure",
          data: {
            source: "run_pipeline",
            execution_status: "skipped",
            runtime_path_type: "no_execution_ready_fail_closed",
            closure_blocker_reason: "no_execution_ready_workflow",
            runtime_path_evidence: {
              retrieval_fail_reason: "no_execution_ready_workflow",
            },
            dispatch_attempted: false,
            dispatch_status: "not_applicable",
            prompt_id: null,
            image_paths: [],
          },
        },
      ],
    }),
    finished: true,
  },
]);
const cachedRawFailureResponse = JSON.parse(cachedRawFailureMessages[0].content);
assert.match(cachedRawFailureResponse.text, /failed_stage: `search`/);
assert.match(cachedRawFailureResponse.text, /failure_reason: `no_execution_ready_workflow`/);
assert.doesNotMatch(cachedRawFailureResponse.text, /unknown/);
assert.equal(
  cachedRawFailureMessages[0].metadata.copilot_cache_schema_version,
  "copilot-message-cache-v3",
);
assert.equal(
  cachedRawFailureMessages[0].metadata.cache_writer_failure_surface_formatter_build_id,
  "20260508-surface-decision-v4",
);
assert.equal(
  cachedRawFailureMessages[0].metadata.failure_surface_generated_formatter_build_id,
  "20260508-surface-decision-v4",
);
assert.equal(cachedRawFailureMessages[0].metadata.failure_surface_formatter_build_id, undefined);

const cachedFailedWorkflowUpdateMessages = storageHelpers.sanitizeFailureSurfaceCacheMessages([
  {
    id: "cached-failed-workflow-update",
    role: "ai",
    content: JSON.stringify({
      text: "old workflow update formatter text",
      finished: true,
      format: "markdown",
      ext: [
        {
          type: "workflow_update",
          data: {
            source: "run_pipeline",
            execution_status: "failed",
            runtime_path_type: "direct_prompt_bypass",
            closure_blocker_reason: "blocked_by_test",
            dispatch_attempted: false,
            dispatch_status: "not_applicable",
            prompt_id: null,
            image_paths: [],
            run_id: "failed-workflow-update",
          },
        },
      ],
    }),
    finished: true,
  },
]);
const cachedFailedWorkflowUpdateResponse = JSON.parse(cachedFailedWorkflowUpdateMessages[0].content);
assert.match(cachedFailedWorkflowUpdateResponse.text, /failed_stage: `router`/);
assert.match(cachedFailedWorkflowUpdateResponse.text, /failure_reason: `blocked_by_test`/);
assert.doesNotMatch(cachedFailedWorkflowUpdateResponse.text, /unknown/);
assert.deepEqual(
  storageHelpers.sanitizeFailureSurfaceCacheMessages(cachedFailedWorkflowUpdateMessages),
  cachedFailedWorkflowUpdateMessages,
);

const staleRenderedFailureMessages = storageHelpers.sanitizeFailureSurfaceCacheMessages([
  {
    id: "cached-rendered-unknown",
    role: "ai",
    content: JSON.stringify({
      text: [
        "### Run Failed Before Image Generation",
        "",
        "- failed_stage: `unknown`",
        "- failure_reason: `unknown`",
      ].join("\n"),
      finished: true,
      format: "markdown",
      ext: [{ type: "node_install_guide", data: { package: "kept" } }],
    }),
    finished: true,
  },
]);
const staleRenderedFailureResponse = JSON.parse(staleRenderedFailureMessages[0].content);
assert.match(staleRenderedFailureResponse.text, /Cached Failure Surface Expired/);
assert.doesNotMatch(staleRenderedFailureResponse.text, /failed_stage: `unknown`/);
assert.equal(staleRenderedFailureResponse.ext[0].type, "node_install_guide");
assert.equal(staleRenderedFailureMessages[0].metadata.stale_failure_surface_invalidated, true);
assert.equal(
  staleRenderedFailureMessages[0].metadata.copilot_cache_schema_version,
  "copilot-message-cache-v3",
);
assert.equal(
  staleRenderedFailureMessages[0].metadata.failure_surface_generated_formatter_build_id,
  "20260508-surface-decision-v4",
);

const staleJsonUnknownMessages = storageHelpers.sanitizeFailureSurfaceCacheMessages([
  {
    id: "cached-json-unknown",
    role: "ai",
    content: JSON.stringify({
      text: "old JSON card",
      failed_stage: "unknown",
      failure_reason: "unknown",
      ext: [],
    }),
    metadata: {
      copilot_cache_schema_version: "copilot-message-cache-v3",
      cache_writer_failure_surface_formatter_build_id: "20260508-surface-decision-v4",
    },
    finished: true,
  },
]);
const staleJsonUnknownResponse = JSON.parse(staleJsonUnknownMessages[0].content);
assert.match(staleJsonUnknownResponse.text, /Cached Failure Surface Expired/);
assert.equal(staleJsonUnknownResponse.failed_stage, undefined);
assert.equal(staleJsonUnknownResponse.failure_reason, undefined);
assert.equal(staleJsonUnknownMessages[0].metadata.stale_failure_surface_invalidated, true);
assert.equal(
  staleJsonUnknownMessages[0].metadata.failure_surface_generated_formatter_build_id,
  "20260508-surface-decision-v4",
);

const localStorageWrites = new Map();
storageSandbox.localStorage = {
  setItem: (key, value) => localStorageWrites.set(key, value),
};
const indexedDbWrites = [];
await storageHelpers.persistFailureSurfaceMessages(
  "persist-session",
  [
    {
      id: "persisted-message",
      role: "ai",
      content: "hello",
      finished: true,
    },
  ],
  async (sessionId, messages) => {
    indexedDbWrites.push({ sessionId, messages });
  },
);
assert.equal(localStorageWrites.has("messages_persist-session"), true);
assert.equal(indexedDbWrites.length, 1);
assert.equal(indexedDbWrites[0].sessionId, "persist-session");
assert.equal(indexedDbWrites[0].messages[0].metadata.copilot_cache_schema_version, "copilot-message-cache-v3");

console.log("failure surface tests passed");
