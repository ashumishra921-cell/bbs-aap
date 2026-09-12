#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Dashboard UPI shortcut, UPI/Cash payment history for subscribers/admin, complaint/payment receive tones. User opted OUT of new cash entry and pending four earlier features. Also reported Super Admin activated plans not appearing in subscriber app."
backend:
  - task: "Role-scoped unified payment history and activity snapshots"
    implemented: true
    working: true
    file: "backend/payment_activity.py"
    stuck_count: 0
    priority: high
    needs_retesting: false
    status_history:
      - agent: main
        working: NA
        comment: "Added /api/payment-history (UPI/Cash/free invoices + unmatched UPI requests, deduplicated on invoice_id, filters/search/pagination) and /api/activity (role-scoped ID/version snapshots, no mutations)."
      - agent: testing
        working: true
        comment: "Iter8/9 verify auth, isolation, literal search, mode filters, pagination, dedupe and team activity scope. Roles restored and regression passes."
frontend:
  - task: "Subscriber live plan visibility"
    implemented: true
    working: true
    file: "frontend/app/(subscriber)/home.tsx"
    stuck_count: 0
    priority: high
    needs_retesting: false
    status_history:
      - agent: user
        working: false
        comment: "Super Admin activates plan but subscriber app does not show it."
      - agent: main
        working: NA
        comment: "RCA confirmed backend correct; added foreground focused 10s polling, resume refresh, network error/retry without false no-plan state."
      - agent: testing
        working: true
        comment: "Iter8 verified plan appears on already-open Home after Super Admin assignment without manual refresh/navigation."
  - task: "Dashboard UPI shortcut and shared payment history"
    implemented: true
    working: true
    file: "frontend/app/payment-history.tsx"
    stuck_count: 0
    priority: high
    needs_retesting: false
    status_history:
      - agent: main
        working: NA
        comment: "Dashboard UPI card for customer/admin, read-only history All/UPI/Cash/Free, search, pagination, invoices with payment mode. Existing screenshot approval unchanged, no new cash entry."
      - agent: testing
        working: true
        comment: "Iter9 confirms admin/subscriber history, invoice mode, search/filters, admin read-only queue vs Super approval controls; modal verified390x844 and320x700."
  - task: "Foreground complaint and payment alert tones"
    implemented: true
    working: true
    file: "frontend/src/components/ActivityAlerts.tsx"
    stuck_count: 0
    priority: high
    needs_retesting: false
    status_history:
      - agent: main
        working: NA
        comment: "Bundled original WAV tones via expo-audio. Root provider, ID/version comparison, first load silent, per-user persisted mute, test buttons, 10s foreground polls; no mic or background audio permissions."
      - agent: testing
        working: true
        comment: "Iter9 automatic complaint/payment playback, silent baseline/unchanged polls, mute persistence/isolation, subscriber-local status/review events passed. Physical phone speaker behavior not tested."
metadata:
  created_by: main_agent
  version: "1.0"
  test_sequence: 9
  run_ui: true
test_plan:
  current_focus:
    - "Live subscriber plan update from Super Admin assignment, without navigation/manual refresh"
    - "UPI/Cash history and role isolation, deduplication and filters"
    - "Automatic complaint/payment tone, no replay on unchanged polls, mute persistence, logout isolation"
    - "Dashboard shortcuts + existing UPI screenshot approval regression"
  stuck_tasks: []
  test_all: false
  test_priority: high_first
agent_communication:
  - agent: main
    message: "TypeScript and changed-file JS/Python lint pass. 390x844 preview login screenshot passes. Test only current scope; leave earlier Expiry SMS, Collection Report, Technician Location, Plan Editor testing deferred. Read memory/test_credentials.md, update for any test accounts created; do not alter production auth."
  - agent: testing
    message: "Iteration8: 10/11 backend assertions passed; live plan updates passed. Missing seeded Admin/Team fixtures recreated as subscriber by OTP. UI stopped at Recharge modal close; automatic audio/admin flows incomplete. Report iteration_8.json."
  - agent: main
    message: "Critical test fixtures repaired via explicit operator script restricted to exact IDs (restore_test_staff.py), NOT startup/login escalation. Auth playbook followed; both Admin and Team curl logins now pass. Correct DB is broadband_247 with data (troubleshooter accidentally inspected wrong DB). Recorded all iter8 credentials. Recharge uses dimension-constrained sheet with flex scroll, pinned footer and top close. Self-test at390x844 confirms cancel button inside viewport and closes sheet; both actual complaint/payment audio playback status events observed; Cash history works. New lint and TypeScript pass. Remaining: automatic new complaint/payment tones, mute/no replay/role-switch isolation, actual Admin read-only payment queue, admin filters/invoice drilldown. Retest is for critical fixture fix + previously blocked initial implementation verification."
  - agent: main
    message: "Iteration9 all requested critical flows pass. Addressed optional findings: explicit ON/OFF and accessibility checked state; screenshot images render only with token. Final mobile self-test verifies toggle state and actual screenshot image pixels, 3 authenticated image responses HTTP200, zero observed401s. Report iteration_9.json reviewed; tester changed only tests/reports/credentials. No new integration mocked; existing demo OTP and deferred previous features unchanged."