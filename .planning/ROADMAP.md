# Roadmap — AndreyVPN_bot

## Phases

- [ ] **Phase 1: Foundation & Data Layer** - Establish project structure and persistence.
- [ ] **Phase 2: Bot Core & Access Control** - Implement onboarding, CAPTCHA, and admin approval.
- [ ] **Phase 3: VPN Service Integration** - Implement AmneziaWG profile generation logic.
- [ ] **Phase 4: Profile Delivery Workflow** - Handle VPN requests and deliver QR/conf files.
- [ ] **Phase 5: Monitoring & Status** - Implement traffic tracking and server health checks.

## Phase Details

### Phase 1: Foundation & Data Layer
**Goal**: Project scaffolding and database schema initialized.
**Depends on**: Nothing
**Requirements**: DATA-01
**Success Criteria**:
  1. Database file `bot_data.db` is created automatically on first run.
  2. All required tables (users, configs, stats) are present in the schema.
  3. Bot starts and logs "Database initialized" successfully.
**Plans**: TBD

### Phase 2: Bot Core & Access Control
**Goal**: Secure onboarding process with admin oversight.
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-03
**Success Criteria**:
  1. New users are blocked by a CAPTCHA challenge upon `/start`.
  2. Admin receives a Telegram notification with "Approve/Reject" buttons for new users.
  3. Only "Approved" users can access the main menu; others receive an "Access Denied" message.
**Plans**: TBD

### Phase 3: VPN Service Integration
**Goal**: Programmatic management of AmneziaWG peers.
**Depends on**: Phase 1
**Requirements**: VPN-01
**Success Criteria**:
  1. Bot can generate unique private/public key pairs for AmneziaWG.
  2. Bot can generate a valid AmneziaWG peer configuration string.
  3. Peer configurations are successfully saved to the database.
**Plans**: TBD

### Phase 4: Profile Delivery Workflow
**Goal**: End-to-end VPN configuration request and delivery.
**Depends on**: Phase 2, Phase 3
**Requirements**: VPN-02, VPN-03
**Success Criteria**:
  1. Approved users can request a new VPN configuration via the bot UI.
  2. Admin must approve each specific configuration request before it is issued.
  3. User receives both a QR code image and a `.conf` file upon approval.
**Plans**: TBD

### Phase 5: Monitoring & Status
**Goal**: Visibility into server health and bandwidth usage.
**Depends on**: Phase 4
**Requirements**: MONITOR-01, MONITOR-02, MONITOR-03
**Success Criteria**:
  1. Users can view their current month's traffic consumption via a `/stats` command.
  2. Admin can check the "Server Status" (AmneziaWG interface Up/Down) via the bot.
  3. Traffic counters reset to zero automatically at 00:00 on the 1st of every month.
**Plans**: TBD

## Progress Tracking

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Data Layer | 0/1 | Not started | - |
| 2. Bot Core & Access Control | 0/1 | Not started | - |
| 3. VPN Service Integration | 0/1 | Not started | - |
| 4. Profile Delivery Workflow | 0/1 | Not started | - |
| 5. Monitoring & Status | 0/1 | Not started | - |

---
*Last updated: 2026-02-24*
