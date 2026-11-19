# Brave Leo Workspace inline file preview

Feature ID: `feature-6fb0b80cc22ad6810a9ee5b2`

Status: **Watch**. Confirmed in the Nightly source. Not tested in an installed browser.

## Change

Before, the conversation showed a button that opened a separate file preview.
The source in Nightly 1.102.21 can also show a workspace file inside the
conversation. The existing button stays available.

The release note identifies the version but does not describe this change.
The [official tag comparison](https://github.com/brave/brave-core/compare/v1.102.20...v1.102.21) confirms the source change between
Nightly 1.102.20 and 1.102.21. The inspected Beta 1.101.52 and Stable 1.100.58
tags still use the prior code.

## Limits and follow-up

Installed availability, default state, supported platforms, and availability in
Korea are not confirmed. When an installed build exposes the feature, check
whether a workspace file appears in the conversation and whether the separate
preview still opens.

- [Official implementation PR](https://github.com/brave/brave-core/pull/41796)
- [Brave Nightly 1.102.21 release](https://github.com/brave/brave-browser/releases/tag/v1.102.21)
- [Nightly source observation](../../data/events/event-e1e65854d55611ed155400c5.json)
