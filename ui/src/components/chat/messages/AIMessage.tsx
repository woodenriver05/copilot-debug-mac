// Copyright (C) 2025 AIDC-AI
// Licensed under the MIT License.
// Copyright (C) 2025 ComfyUI-Copilot Authors
// Licensed under the MIT License.

import React, { useEffect } from 'react'
import { BaseMessage } from './BaseMessage';
import { ChatResponse } from "../../../types/types";
import { useRef } from "react";
import Markdown from '../../ui/Markdown';

interface AIMessageProps {
  content: string;
  name?: string;
  avatar: string;
  format?: string;
  onOptionClick?: (option: string) => void;
  extComponent?: React.ReactNode;
  metadata?: any;
  finished?: boolean;
  debugGuide?: boolean;
}

// Card component for node explanation intent
const NodeExplainCard = ({ content }: { content: React.ReactNode }) => {
  return (
    <div className="rounded-lg shadow-sm">
      <div className="flex items-center mb-1">
        <div className="rounded-full mr-1">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h3 className="text-base font-bold">Node Usage Guide</h3>
      </div>
      <div className="markdown-content">
        {content}
      </div>
    </div>
  );
};

// Card component for node parameters intent
const NodeParamsCard = ({ content }: { content: React.ReactNode }) => {
  return (
    <div className="rounded-lg border border-green-200 bg-green-50 p-1 shadow-sm">
      <div className="flex items-center mb-1">
        <div className="bg-green-100 rounded-full p-1 mr-1">
          <svg className="h-4 w-4 text-green-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </div>
        <h3 className="text-sm font-medium text-green-800">Node Parameter Reference</h3>
      </div>
      <div className="markdown-content text-green-900">
        {content}
      </div>
    </div>
  );
};

export function AIMessage({ content, name = 'Assistant', avatar, format, onOptionClick, extComponent, metadata, finished, debugGuide }: AIMessageProps) {
  const markdownWrapper = useRef<HTMLDivElement | null>(null)

  const renderContent = () => {
    try {
      const response = JSON.parse(content) as ChatResponse;
      const guides = response.ext?.find(item => item.type === 'guides')?.data || [];
      
      // 检查是否有实时更新的ext数据
      const hasWorkflowUpdate = response.ext?.some(item => item.type === 'workflow_update');
      const hasParamUpdate = response.ext?.some(item => item.type === 'param_update');

      // Check if this is a special message type based on intent metadata
      if (metadata?.intent) {
        const intent = metadata.intent;
        
        // Render different card styles based on intent
        // Only handle node_explain and node_params with card styles
        if (intent === 'node_explain') {
          return (
            <NodeExplainCard 
              content={<Markdown response={response || {}} />}
            />
          );
        } else if (intent === 'node_params') {
          return (
            <NodeParamsCard 
              content={<Markdown response={response || {}} />}
            />
          );
        }
        // The downstream_subgraph_search intent is handled by the extComponent in MessageList.tsx
        // and doesn't need special card rendering here
      }

      // Default rendering for regular conversation messages
      return (
        <div className="space-y-3">
          {format === 'markdown' && response.text ? (
            <div ref={markdownWrapper as React.RefObject<HTMLDivElement>}>
              <Markdown response={response || {}} />
            </div>
          ) : response.text ? (
            <p className="whitespace-pre-wrap text-left">
              {response.text}
            </p>
          ) : null}

          {guides.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {guides.map((guide: string, index: number) => (
                <button
                  key={index}
                  className="px-3 py-1.5 text-gray-700 rounded-md hover:!bg-gray-50 transition-colors text-[12px] w-[calc(50%-0.25rem)] border border-gray-700"
                  onClick={() => onOptionClick?.(guide)}
                >
                  {guide}
                </button>
              ))}
            </div>
          )}

          {extComponent}
        </div>
      );
    } catch {
      return <p className="whitespace-pre-wrap text-left">{content}</p>;
    }
  };

  return (
    <BaseMessage name={name}>
      <div className="w-full rounded-lg bg-gray-50 p-4 text-gray-900 text-sm break-words overflow-hidden">
        {renderContent()}
        {debugGuide && !finished && (
            <div className="flex items-center gap-2 text-blue-500 text-sm">
                <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full"></div>
                Analyzing workflow...
            </div>
        )}
        
        {/* 显示实时更新状态 */}
        {(() => {
          try {
            const response = JSON.parse(content) as ChatResponse;
            const hasWorkflowUpdate = response.ext?.some(item => item.type === 'workflow_update');
            const hasParamUpdate = response.ext?.some(item => item.type === 'param_update');
            
            if (!finished && (hasWorkflowUpdate || hasParamUpdate)) {
              return (
                <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg">
                  <div className="flex items-center gap-2 text-green-700 text-sm">
                    <svg className="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span className="font-medium">
                      {hasWorkflowUpdate ? 'Workflow Updated' : 'Parameters Updated'}
                    </span>
                  </div>
                  <div className="text-xs text-green-600 mt-1">
                    Changes have been applied to the canvas. Debug process continues...
                  </div>
                </div>
              );
            }
          } catch (error) {
            // Ignore parsing errors
          }
          return null;
        })()}
      </div>
    </BaseMessage>
  );
} 