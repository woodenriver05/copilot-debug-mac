// Copyright (C) 2025 AIDC-AI
// Licensed under the MIT License.

import type { Message } from '../types/types';
import {
  FAILURE_SURFACE_FORMATTER_BUILD_ID,
  FAILURE_SURFACE_SCHEMA_VERSION,
} from '../components/chat/failureSurface';
import { FAILURE_SURFACE_CACHE_SCHEMA_VERSION } from './failureSurfaceStorageDebug';

export interface ChatSession {
  id: string;
  firstMessage: string;
  lastUpdated: number;
  messages: Message[];
  cacheSchemaVersion?: string;
  failureSurfaceSchemaVersion?: string;
  failureSurfaceFormatterBuildId?: string;
}

class IndexedDBManager {
  private dbName = 'ComfyUICopilotDB';
  private version = 1;
  private storeName = 'chatSessions';
  private db: IDBDatabase | null = null;

  async init(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.version);

      request.onerror = () => {
        reject(new Error('Failed to open IndexedDB'));
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // Create object store for chat sessions
        if (!db.objectStoreNames.contains(this.storeName)) {
          const store = db.createObjectStore(this.storeName, { keyPath: 'id' });
          store.createIndex('lastUpdated', 'lastUpdated', { unique: false });
        }
      };
    });
  }

  async saveSession(sessionId: string, messages: Message[]): Promise<void> {
    if (!this.db) {
      await this.init();
    }

    if (!this.db) {
      throw new Error('Database not initialized');
    }

    const firstMessage = messages.find(m => m.role === 'user')?.content || '';
    const session: ChatSession = {
      id: sessionId,
      firstMessage: firstMessage.length > 50 ? firstMessage.substring(0, 50) + '...' : firstMessage,
      lastUpdated: Date.now(),
      messages: messages,
      cacheSchemaVersion: FAILURE_SURFACE_CACHE_SCHEMA_VERSION,
      failureSurfaceSchemaVersion: FAILURE_SURFACE_SCHEMA_VERSION,
      failureSurfaceFormatterBuildId: FAILURE_SURFACE_FORMATTER_BUILD_ID,
    };

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.storeName], 'readwrite');
      const store = transaction.objectStore(this.storeName);
      const request = store.put(session);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(new Error('Failed to save session'));
    });
  }

  async getSession(sessionId: string): Promise<ChatSession | null> {
    if (!this.db) {
      await this.init();
    }

    if (!this.db) {
      throw new Error('Database not initialized');
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.storeName], 'readonly');
      const store = transaction.objectStore(this.storeName);
      const request = store.get(sessionId);

      request.onsuccess = () => {
        resolve(request.result || null);
      };
      request.onerror = () => reject(new Error('Failed to get session'));
    });
  }

  async getAllSessions(): Promise<ChatSession[]> {
    if (!this.db) {
      await this.init();
    }

    if (!this.db) {
      throw new Error('Database not initialized');
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.storeName], 'readonly');
      const store = transaction.objectStore(this.storeName);
      const index = store.index('lastUpdated');
      const request = index.openCursor(null, 'prev'); // 按时间倒序

      const sessions: ChatSession[] = [];

      request.onsuccess = () => {
        const cursor = request.result;
        if (cursor) {
          sessions.push(cursor.value);
          cursor.continue();
        } else {
          resolve(sessions);
        }
      };
      request.onerror = () => reject(new Error('Failed to get all sessions'));
    });
  }

  async deleteSession(sessionId: string): Promise<void> {
    if (!this.db) {
      await this.init();
    }

    if (!this.db) {
      throw new Error('Database not initialized');
    }

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([this.storeName], 'readwrite');
      const store = transaction.objectStore(this.storeName);
      const request = store.delete(sessionId);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(new Error('Failed to delete session'));
    });
  }
}

export const indexedDBManager = new IndexedDBManager();
