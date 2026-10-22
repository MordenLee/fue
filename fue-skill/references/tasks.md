# Delegate a research task

Use a model ID already configured in FUE and explicit library IDs. Model credentials stay in Core. Create a UTF-8 JSON task file containing only the requested goal and task configuration:

```json
{
  "request_key": "a-unique-stable-key-for-this-submission",
  "goal": "Compare the selected literature and identify supporting evidence and gaps.",
  "model_id": 32,
  "kb_ids": [3],
  "max_tool_calls": 5,
  "max_model_calls": 5,
  "timeout_seconds": 180,
  "input_tokens": 48000,
  "output_tokens": 8192
}
```

The numeric model/library IDs above are examples, not defaults to assume for another installation. Never copy the host's full conversation into `goal`. Tasks currently use document scope; FUE history reads are available separately through Direct mode.

```text
python <skill>/scripts/fue.py --auto-start tasks submit --file task.json --json
python <skill>/scripts/fue.py tasks get TASK_ID --after 0 --json
python <skill>/scripts/fue.py tasks cancel TASK_ID --json
```

Keep `request_key` stable when retrying a submission after a connection failure; it prevents duplicate execution. Changing the payload under the same key is a conflict. A deliberate rerun uses a new key.

Read event pages using `last_sequence` and `more_events`. Report actual state and available usage; estimates are not bills. A retrieved-evidence list includes search hits and is not proof that every source was fully read. The task result includes citations and stable references that can be read again through the Dataset API.

Cancellation stops further task execution and prevents a late success result. A provider may still complete a request already sent. After a Core restart, unfinished tasks are `interrupted`; do not automatically resubmit paid work. Display the interruption and follow the user's instruction.
