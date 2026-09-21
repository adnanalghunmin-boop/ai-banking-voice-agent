# Breez Call Display

A MENADEVS-branded local Chrome extension that replaces Breez's small test-call panel with a polished, full-screen presentation while keeping Breez responsible for the microphone, audio, agent logic, and authentication.

## Install on Chrome (Ubuntu)

1. Extract `breez-call-display.zip`.
2. Open `chrome://extensions` in Chrome.
3. Enable **Developer mode** in the upper-right corner.
4. Click **Load unpacked**.
5. Select the extracted `breez-call-display` folder (the folder containing `manifest.json`).
6. Reload the open Breez tab.
7. Open a workflow and click **Test**. The display opens automatically when the Breez audio WebSocket starts.

The call presentation opens directly in full-screen mode. The live transcript stays inside a fixed three-line area so the interface does not shift as the text changes.

## Controls

- Microphone button: mute/unmute the existing Breez microphone track.
- **End call**: ends the WebSocket session and clicks Breez's native **End Test** button when available.
- Minus button: hides the display without ending the call.
- `Ctrl+Shift+B`: show or hide the display.

## Current Breez event mapping

- `transcript_update`: live/final text, role, segment, and timestamps.
- `agent_state`: `listening`, `thinking`, or `speaking`.
- `agent_speaking`: explicit assistant speech start/stop.

## Privacy

The extension has no analytics and sends data nowhere. It runs only on `https://app.heybreez.ai/*`. It does not store or request tokens, cookies, transcripts, or audio. All call traffic remains between the existing Breez page and Breez services.

## Notes

- This integration observes Breez's current internal browser-test protocol. Breez may change that protocol without notice.
- The visible name and colors can be edited in `display.js` and `display.css`.
- Use the display for authorized workflows and test calls only.
