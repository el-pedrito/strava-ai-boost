#!/bin/bash

# Replay an activity through the Step Functions pipeline
#
# Re-runs an activity from the input of its LATEST execution (the manual
# procedure of 2026-10-09, activity 20518589504 lost to a transient 502).
# The new execution is named activity-<id>-replay-<epoch>, so it never
# collides with the deterministic activity-<id>-v<event_time> names the
# activity processor uses.
#
# Usage: scripts/replay_activity.sh <activity_id> [--yes]
#   AWS_PROFILE / AWS_REGION are honoured when set (region defaults to us-east-1).
#   STATE_MACHINE_NAME overrides the state machine (default StravaAIBoost-ActivityProcessing).

set -euo pipefail

ACTIVITY_ID="${1:-}"
ASSUME_YES="${2:-}"

if [[ -z "$ACTIVITY_ID" || ! "$ACTIVITY_ID" =~ ^[0-9]+$ ]]; then
    echo "Usage: $0 <activity_id> [--yes]" >&2
    echo "  activity_id must be the numeric Strava activity id" >&2
    exit 1
fi

PROFILE="${AWS_PROFILE:-}"
# Only pass --profile when one is configured; otherwise rely on ambient
# credentials (environment variables, instance role, container role...).
if [ -n "$PROFILE" ]; then
    PROFILE_ARGS=(--profile "$PROFILE")
else
    PROFILE_ARGS=()
fi
REGION="${AWS_REGION:-us-east-1}"
STATE_MACHINE_NAME="${STATE_MACHINE_NAME:-StravaAIBoost-ActivityProcessing}"

aws_cli() {
    aws "$@" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} --region "$REGION"
}

STATE_MACHINE_ARN=$(aws_cli stepfunctions list-state-machines \
    --query "stateMachines[?name=='${STATE_MACHINE_NAME}'].stateMachineArn | [0]" \
    --output text)
if [[ -z "$STATE_MACHINE_ARN" || "$STATE_MACHINE_ARN" == "None" ]]; then
    echo "State machine ${STATE_MACHINE_NAME} not found in ${REGION}" >&2
    exit 1
fi

# Latest execution of this activity, whatever its naming scheme (timestamp,
# v<event_time> or a previous replay): all start with activity-<id>-.
# --query runs per page with text output, so sort the (startDate, arn) lines here.
LATEST_ARN=$(aws_cli stepfunctions list-executions \
    --state-machine-arn "$STATE_MACHINE_ARN" \
    --query "executions[?starts_with(name, 'activity-${ACTIVITY_ID}-')].[startDate, executionArn]" \
    --output text | sort -r | head -n 1 | cut -f2)
if [[ -z "$LATEST_ARN" || "$LATEST_ARN" == "None" ]]; then
    echo "No execution found for activity ${ACTIVITY_ID}" >&2
    exit 1
fi

LATEST_STATUS=$(aws_cli stepfunctions describe-execution \
    --execution-arn "$LATEST_ARN" --query status --output text)
INPUT=$(aws_cli stepfunctions describe-execution \
    --execution-arn "$LATEST_ARN" --query input --output text)

echo "Activity:          ${ACTIVITY_ID}"
echo "Latest execution:  ${LATEST_ARN} (${LATEST_STATUS})"

if [[ "$LATEST_STATUS" == "RUNNING" ]]; then
    echo "The latest execution is still RUNNING, refusing to start a concurrent replay" >&2
    exit 1
fi

NEW_NAME="activity-${ACTIVITY_ID}-replay-$(date +%s)"
echo "New execution:     ${NEW_NAME}"

if [[ "$ASSUME_YES" != "--yes" ]]; then
    read -r -p "Start the replay? This rewrites the activity on Strava. [y/N] " answer
    if [[ ! "$answer" =~ ^[yY]$ ]]; then
        echo "Aborted"
        exit 0
    fi
fi

aws_cli stepfunctions start-execution \
    --state-machine-arn "$STATE_MACHINE_ARN" \
    --name "$NEW_NAME" \
    --input "$INPUT" \
    --query executionArn --output text
