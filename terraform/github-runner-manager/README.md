# GitHub Runner Manager

  ┌─────────────┐        ┌──────────────────────────────────────┐
  │   GitHub    │───────▶│  Cloud Run Service
  │
  │  Webhooks   │        │                                      │
  └─────────────┘        │  POST /github/webhook                │
                         │    ↓                                 │
                         │    ├→ POST /runner/start (必要なら) │
                         │    └→ Cloud Tasks: /runner/stop      │
                         │       (15分後、古いタスクは削除)
  │
                         │                                      │
                         │  POST /runner/start                  │
                         │    - VM起動                          │
                         │                                      │
                         │  POST /runner/stop                   │
                         │    - VM停止                          │
                         └──────────────────────────────────────┘
                                        ↓
                                ┌──────────────┐
                                │ Cloud Tasks  │
                                │ (15分後実行) │
                                └──────────────┘
