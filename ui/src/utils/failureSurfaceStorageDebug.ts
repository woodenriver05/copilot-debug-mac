import type { Message } from "../types/types";
import {
  buildRunPipelineFailureMarkdown,
  FAILURE_SURFACE_FORMATTER_BUILD_ID,
  FAILURE_SURFACE_SCHEMA_VERSION,
  findRunPipelineFailureExt,
  getRunPipelineFailureDebugSummary,
  isRunPipelineFailureExt,
} from "../components/chat/failureSurface";

export const FAILURE_SURFACE_CACHE_SCHEMA_VERSION = "copilot-message-cache-v3";
const DB_NAME = "ComfyUICopilotDB";
const STORE_NAME = "chatSessions";
const FAILURE_FINGERPRINT_PATTERN =
  /run_pipeline_failure|Run Failed Before Image Generation|failed_stage|failure_reason|no_execution_ready_workflow/i;
const UNKNOWN_FAILURE_PATTERN = /["']?(?:failed_stage|failure_reason)["']?\s*[:=]\s*["`']?unknown["`']?/i;
const RAW_RUN_PIPELINE_PATTERN =
  /workflow_update|["']source["']\s*:\s*["']run_pipeline["']|["']execution_status["']\s*:\s*["'](?:failed|skipped)["']/i;
const STALE_FAILURE_SURFACE_TEXT = [
  "### Cached Failure Surface Expired",
  "",
  "This cached failure card was created by an older formatter and did not preserve raw run evidence.",
  "Rerun the request to inspect current failure evidence.",
].join("\n");

type StoredMessageSummary = {
  id?: string;
  role?: string;
  finished?: boolean;
  metadata?: any;
  ext_types: string[];
  has_run_pipeline_failure_ext: boolean;
  contains_failure_fingerprint: boolean;
  contains_unknown_failure_text: boolean;
  failure_surface: ReturnType<typeof getRunPipelineFailureDebugSummary>;
  content_preview: string;
};

type StorageReport = {
  session_id: string | null;
  cache_schema_version: string;
  surface_schema_version: string;
  formatter_build_id: string;
  memory: {
    found: boolean;
    message_count: number;
    failure_messages: StoredMessageSummary[];
    error: string | null;
  };
  local_storage: {
    key: string | null;
    message_count: number;
    failure_messages: StoredMessageSummary[];
    parse_error: string | null;
  };
  indexed_db: {
    db_name: string;
    store_name: string;
    found: boolean;
    message_count: number;
    failure_messages: StoredMessageSummary[];
    error: string | null;
  };
};

type SaveSession = (sessionId: string, messages: Message[]) => Promise<void>;

declare global {
  interface Window {
    __copilotFailureSurfaceDebug?: {
      cache_schema_version: string;
      surface_schema_version: string;
      formatter_build_id: string;
      exportCurrentSession: () => Promise<StorageReport>;
    };
  }
}

let memoryMessagesReader: (() => Message[]) | null = null;

function cacheWriterMetadata() {
  return {
    copilot_cache_schema_version: FAILURE_SURFACE_CACHE_SCHEMA_VERSION,
    cache_writer_failure_surface_schema_version: FAILURE_SURFACE_SCHEMA_VERSION,
    cache_writer_failure_surface_formatter_build_id: FAILURE_SURFACE_FORMATTER_BUILD_ID,
  };
}

function generatedFailureSurfaceMetadata() {
  return {
    failure_surface_generated_schema_version: FAILURE_SURFACE_SCHEMA_VERSION,
    failure_surface_generated_formatter_build_id: FAILURE_SURFACE_FORMATTER_BUILD_ID,
  };
}

export function annotateFailureSurfaceCacheMessages(messages: Message[]): Message[] {
  return messages.map((message) => ({
    ...message,
    metadata: {
      ...(message.metadata || {}),
      ...cacheWriterMetadata(),
    },
  }));
}

function hasCurrentFailureSurfaceGeneratedMetadata(message: Message): boolean {
  return (
    message.metadata?.failure_surface_generated_schema_version === FAILURE_SURFACE_SCHEMA_VERSION &&
    message.metadata?.failure_surface_generated_formatter_build_id === FAILURE_SURFACE_FORMATTER_BUILD_ID
  );
}

function getRawMessageContent(message: Message): string {
  return typeof message.content === "string" ? message.content : JSON.stringify(message.content ?? "");
}

function hasFailureSurfaceFingerprint(rawContent: string): boolean {
  return (
    FAILURE_FINGERPRINT_PATTERN.test(rawContent) ||
    UNKNOWN_FAILURE_PATTERN.test(rawContent) ||
    RAW_RUN_PIPELINE_PATTERN.test(rawContent)
  );
}

function buildStaleFailureSurfaceContent(parsedContent: any | null): string {
  if (parsedContent && typeof parsedContent === "object") {
    const retainedExt = Array.isArray(parsedContent.ext)
      ? parsedContent.ext.filter((item: any) => !isRunPipelineFailureExt(item))
      : [];
    const {
      ext: _ext,
      failed_stage: _failedStage,
      failure_reason: _failureReason,
      typed_failure: _typedFailure,
      runtime_path_evidence: _runtimePathEvidence,
      ...safeContent
    } = parsedContent;
    return JSON.stringify({
      ...safeContent,
      text: STALE_FAILURE_SURFACE_TEXT,
      ext: retainedExt,
    });
  }
  return STALE_FAILURE_SURFACE_TEXT;
}

export function sanitizeFailureSurfaceCacheMessages(messages: Message[]): Message[] {
  return annotateFailureSurfaceCacheMessages(
    messages.map((message) => {
      const rawContent = getRawMessageContent(message);
      const shouldInspectMessage = hasFailureSurfaceFingerprint(rawContent);
      const parsedContent = shouldInspectMessage ? parseMessageContent(message) : null;
      const failureExt = parsedContent ? findRunPipelineFailureExt(parsedContent) : undefined;

      if (failureExt) {
        return {
          ...message,
          metadata: {
            ...(message.metadata || {}),
            ...generatedFailureSurfaceMetadata(),
          },
          content: JSON.stringify({
            ...(parsedContent || {}),
            text: buildRunPipelineFailureMarkdown(failureExt.data || {}),
          }),
        };
      }

      const hasStaleUnknownFailureCard =
        message.role !== "user" &&
        !hasCurrentFailureSurfaceGeneratedMetadata(message) &&
        FAILURE_FINGERPRINT_PATTERN.test(rawContent) &&
        UNKNOWN_FAILURE_PATTERN.test(rawContent);

      if (!hasStaleUnknownFailureCard) {
        return message;
      }

      return {
        ...message,
        content: buildStaleFailureSurfaceContent(parsedContent),
        metadata: {
          ...(message.metadata || {}),
          ...generatedFailureSurfaceMetadata(),
          stale_failure_surface_invalidated: true,
          stale_failure_surface_invalidated_at: new Date().toISOString(),
        },
      };
    }),
  );
}

export async function persistFailureSurfaceMessages(
  sessionId: string | null,
  messages: Message[],
  saveSession?: SaveSession,
): Promise<Message[]> {
  const messagesForCache = annotateFailureSurfaceCacheMessages(messages);

  if (!sessionId) {
    return messagesForCache;
  }

  if (typeof localStorage !== "undefined") {
    localStorage.setItem(`messages_${sessionId}`, JSON.stringify(messagesForCache));
  }

  if (saveSession) {
    try {
      await saveSession(sessionId, messagesForCache);
    } catch (error) {
      if (typeof console !== "undefined") {
        console.error("Failed to save session to IndexedDB:", error);
      }
    }
  }

  return messagesForCache;
}

function safeParseJson(value: string): { value: any; error: string | null } {
  try {
    return { value: JSON.parse(value), error: null };
  } catch (error) {
    return { value: null, error: error instanceof Error ? error.message : String(error) };
  }
}

function parseMessageContent(message: Message): any | null {
  if (typeof message.content !== "string") {
    return null;
  }
  const parsed = safeParseJson(message.content);
  return parsed.error ? null : parsed.value;
}

function compactPreview(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? "");
  return text.length > 600 ? `${text.slice(0, 600)}...` : text;
}

function summarizeMessages(messages: Message[]): StoredMessageSummary[] {
  return messages
    .map((message) => {
      const rawContent = getRawMessageContent(message);
      const contentPreview = compactPreview(rawContent);
      const containsFailureFingerprint = FAILURE_FINGERPRINT_PATTERN.test(rawContent);
      const containsUnknownFailureText = UNKNOWN_FAILURE_PATTERN.test(rawContent);
      if (!containsFailureFingerprint && !containsUnknownFailureText) {
        return null;
      }

      const parsedContent = parseMessageContent(message);
      const extItems = Array.isArray(parsedContent?.ext) ? parsedContent.ext : [];
      const extTypes = extItems.map((item: any) => item?.type).filter(Boolean);
      const failureExt = parsedContent ? findRunPipelineFailureExt(parsedContent) : undefined;

      return {
        id: message.id,
        role: message.role,
        finished: message.finished,
        metadata: message.metadata || null,
        ext_types: extTypes,
        has_run_pipeline_failure_ext: Boolean(failureExt),
        contains_failure_fingerprint: containsFailureFingerprint,
        contains_unknown_failure_text: containsUnknownFailureText,
        failure_surface: parsedContent ? getRunPipelineFailureDebugSummary(parsedContent) : null,
        content_preview: contentPreview,
      };
    })
    .filter(
      (summary): summary is StoredMessageSummary =>
        Boolean(
          summary &&
            (summary.has_run_pipeline_failure_ext ||
              summary.contains_failure_fingerprint ||
              summary.contains_unknown_failure_text),
        ),
    );
}

function getMemoryMessages(): { messages: Message[]; found: boolean; error: string | null } {
  if (!memoryMessagesReader) {
    return { messages: [], found: false, error: null };
  }

  try {
    const messages = memoryMessagesReader();
    if (!Array.isArray(messages)) {
      return { messages: [], found: true, error: "Memory reader did not return an array" };
    }
    return { messages, found: true, error: null };
  } catch (error) {
    return { messages: [], found: true, error: error instanceof Error ? error.message : String(error) };
  }
}

function getLocalStorageMessages(sessionId: string | null): {
  key: string | null;
  messages: Message[];
  parseError: string | null;
} {
  if (!sessionId || typeof localStorage === "undefined") {
    return { key: null, messages: [], parseError: null };
  }

  const key = `messages_${sessionId}`;
  const rawMessages = localStorage.getItem(key);
  if (!rawMessages) {
    return { key, messages: [], parseError: null };
  }

  const parsed = safeParseJson(rawMessages);
  if (parsed.error || !Array.isArray(parsed.value)) {
    return { key, messages: [], parseError: parsed.error || "messages cache is not an array" };
  }

  return { key, messages: parsed.value, parseError: null };
}

function readIndexedDbSession(sessionId: string | null): Promise<{ messages: Message[]; found: boolean; error: string | null }> {
  return new Promise((resolve) => {
    if (!sessionId || typeof indexedDB === "undefined") {
      resolve({ messages: [], found: false, error: null });
      return;
    }

    const request = indexedDB.open(DB_NAME, 1);
    request.onerror = () => {
      resolve({ messages: [], found: false, error: "Failed to open IndexedDB" });
    };
    request.onsuccess = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.close();
        resolve({ messages: [], found: false, error: null });
        return;
      }

      const transaction = db.transaction([STORE_NAME], "readonly");
      const store = transaction.objectStore(STORE_NAME);
      const sessionRequest = store.get(sessionId);

      sessionRequest.onsuccess = () => {
        const session = sessionRequest.result;
        db.close();
        resolve({
          messages: Array.isArray(session?.messages) ? session.messages : [],
          found: Boolean(session),
          error: null,
        });
      };
      sessionRequest.onerror = () => {
        db.close();
        resolve({ messages: [], found: false, error: "Failed to read chat session" });
      };
    };
    request.onupgradeneeded = () => {
      request.transaction?.abort();
      resolve({ messages: [], found: false, error: "IndexedDB schema is missing" });
    };
  });
}

async function exportCurrentFailureSurfaceSession(): Promise<StorageReport> {
  const sessionId = typeof localStorage === "undefined" ? null : localStorage.getItem("sessionId");
  const memoryMessages = getMemoryMessages();
  const localStorageMessages = getLocalStorageMessages(sessionId);
  const indexedDbSession = await readIndexedDbSession(sessionId);

  return {
    session_id: sessionId,
    cache_schema_version: FAILURE_SURFACE_CACHE_SCHEMA_VERSION,
    surface_schema_version: FAILURE_SURFACE_SCHEMA_VERSION,
    formatter_build_id: FAILURE_SURFACE_FORMATTER_BUILD_ID,
    memory: {
      found: memoryMessages.found,
      message_count: memoryMessages.messages.length,
      failure_messages: summarizeMessages(memoryMessages.messages),
      error: memoryMessages.error,
    },
    local_storage: {
      key: localStorageMessages.key,
      message_count: localStorageMessages.messages.length,
      failure_messages: summarizeMessages(localStorageMessages.messages),
      parse_error: localStorageMessages.parseError,
    },
    indexed_db: {
      db_name: DB_NAME,
      store_name: STORE_NAME,
      found: indexedDbSession.found,
      message_count: indexedDbSession.messages.length,
      failure_messages: summarizeMessages(indexedDbSession.messages),
      error: indexedDbSession.error,
    },
  };
}

export function registerFailureSurfaceMemoryMessagesReader(reader: (() => Message[]) | null): void {
  memoryMessagesReader = reader;
}

export function registerFailureSurfaceStorageDebug(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.__copilotFailureSurfaceDebug = {
    cache_schema_version: FAILURE_SURFACE_CACHE_SCHEMA_VERSION,
    surface_schema_version: FAILURE_SURFACE_SCHEMA_VERSION,
    formatter_build_id: FAILURE_SURFACE_FORMATTER_BUILD_ID,
    exportCurrentSession: exportCurrentFailureSurfaceSession,
  };
}
