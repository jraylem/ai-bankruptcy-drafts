# Post-Parallelization Migration Implementation - Frontend

## Overview

This document describes the frontend implementation of non-blocking parallel pleading generation, migrating from the blocking SSE-based flow to a REST API with polling.

---

## What Was Implemented

### New Files Created

| File | Purpose |
|------|---------|
| `src/types/pleading.ts` | TypeScript types for pleading tasks, statuses, API responses |
| `src/services/pleading.service.ts` | API service for new `/api/pleadings/*` endpoints |
| `src/stores/usePleadingTaskStore.ts` | Zustand store for task state management and polling |
| `src/components/pleading/StatusCard.tsx` | Individual task status card component |
| `src/components/pleading/StatusCardsContainer.tsx` | Container for multiple status cards |
| `src/components/pleading/InputRequiredModal.tsx` | Dynamic form modal for user input during AWAITING_INPUT state |
| `src/components/pleading/CancelConfirmModal.tsx` | Confirmation dialog for cancelling tasks |
| `src/components/pleading/useParallelPleading.ts` | Hook for starting parallel generation |
| `src/components/pleading/index.ts` | Barrel export for pleading components |

### Modified Files

| File | Changes |
|------|---------|
| `src/components/layout/Header.tsx` | Added props for task handlers, conditional status cards display |
| `src/components/chat/ChatContainer.tsx` | Integrated status cards in header area, added modals, task action handlers |
| `src/components/chat/MotionGeneratorModal.tsx` | **Now uses parallel generation API** - closes immediately after queuing |
| `src/stores/usePleadingTaskStore.ts` | Added toast notifications for status changes (AWAITING_INPUT, COMPLETED, FAILED) |
| `src/layouts/DashboardLayout.tsx` | Added active tasks loading on mount |

---

## Architecture

### Task State Machine

```
PENDING → EXTRACTING → AWAITING_INPUT → GENERATING → COMPLETED
    ↓          ↓              ↓              ↓
    └──────────┴──────────────┴──────────────┴──→ FAILED / CANCELLED
```

### Polling Strategy

| State | Polling Interval |
|-------|------------------|
| PENDING | 1 second |
| EXTRACTING | 2 seconds |
| AWAITING_INPUT | No polling (waits for user) |
| GENERATING | 2 seconds |
| COMPLETED | No polling |
| FAILED | No polling |
| CANCELLED | No polling |

---

## Usage

### Starting Parallel Generation

Use the `useParallelPleading` hook:

```typescript
import { useParallelPleading } from '@/components/pleading';

function MyComponent() {
  const { startParallelGeneration, isLoading, error } = useParallelPleading();

  const handleGenerate = async () => {
    const result = await startParallelGeneration({
      sessionId: 'session-123',
      mode: 'generate-modify', // DocumentMode type
      caseName: 'John Smith',
      source: 'gmail', // or 'courtdrive'
      includeService: true,
    });

    if (result.success) {
      // Modal can close - task is now in background
      console.log('Task queued:', result.taskId);
    }
  };
}
```

### Task Status Monitoring

The `ChatContainer` automatically displays status cards when tasks exist. The cards show:
- Task progress (spinning icon during processing)
- "Input" button when user input is needed
- "Open / Email / Save" buttons when complete
- "X" button to cancel (with confirmation)

### Handling User Input

When a task enters `AWAITING_INPUT` state:
1. A toast notification appears
2. The status card shows an "Input" button
3. Clicking "Input" opens `InputRequiredModal`
4. The modal dynamically renders form fields based on `inputRequired.fields`
5. Pre-filled values from `inputRequired.prefilled` are populated
6. Submitting resumes the task

---

## API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `POST /api/pleadings/generate?user_id={id}` | Start new generation |
| `GET /api/pleadings/tasks/{task_id}` | Poll task status |
| `GET /api/pleadings/tasks?user_id={id}&status=active` | List active tasks |
| `POST /api/pleadings/tasks/{task_id}/input` | Submit user input |
| `POST /api/pleadings/tasks/{task_id}/cancel` | Cancel task |
| `GET /api/pleadings/tasks/{task_id}/result` | Get completed result |

---

## Integration Notes

### MotionGeneratorModal Integration (COMPLETED)

The `MotionGeneratorModal` has been updated to use the parallel generation API:

1. When `proceedWithNormalFlow()` is called, it now:
   - Extracts the case name from the active thread
   - Calls `startParallelGeneration()` with the session, mode, and case info
   - Closes the modal immediately on success
   - Shows an error toast on failure

2. The legacy SSE blocking code is preserved but unreachable (kept for reference)

3. Status cards automatically appear in the `ChatContainer` header when tasks are running

### Toast Notifications

The polling logic in `usePleadingTaskStore` now triggers toast notifications when:
- Task enters **AWAITING_INPUT** state: "We need your help verifying information for [case name]"
- Task **COMPLETED**: "[Motion type] for [case name] completed"
- Task **FAILED**: "Generation failed for [case name]: [error message]"

### Backward Compatibility

- Old SSE endpoints remain functional but are no longer called from the modal
- The parallel API handles all motion generation

---

## Testing Checklist

- [ ] Single task generation works end-to-end
- [ ] Multiple concurrent tasks (up to 5) display correctly
- [ ] 429 error shows appropriate message when limit reached
- [ ] Task cancellation works at all states
- [ ] AWAITING_INPUT state shows input form correctly
- [ ] Dynamic form fields render based on backend fields
- [ ] Prefilled values populate in form
- [ ] Input submission resumes generation
- [ ] COMPLETED state shows action buttons
- [ ] "Open" navigates to session
- [ ] Polling starts/stops correctly per state
- [ ] Page refresh loads existing active tasks
- [ ] Logout stops all polling

---

## Known Limitations

1. **Email button**: Currently shows "coming soon" toast - needs integration with existing email workflow
2. **Save button**: Currently shows toast - needs integration with existing edit-before-download workflow
3. **Open button**: Navigates to thread/session if found in local thread list; may fail if thread not loaded

---

## Next Steps

1. Implement email integration in `handleEmailTask`
2. Implement save/edit workflow in `handleSaveTask` (open editor with payload for modification)
3. Improve "Open" action to handle cases where thread isn't in local list
4. Add notification when tasks complete while user is on different page
5. Consider WebSocket for real-time updates instead of polling

---

## Change Log

### Latest Update (Parallel API Integration)

- Modified `MotionGeneratorModal.tsx` to use `useParallelPleading` hook
- Added `getCaseNameFromSession()` helper to extract case name from active thread
- Modified `proceedWithNormalFlow()` to call parallel API and close modal immediately
- Added toast notifications in polling logic for AWAITING_INPUT, COMPLETED, and FAILED states
- Fixed TypeScript errors in legacy code section
- Updated `ChatContainer.tsx` to use `loadThreadMessages` for navigation
