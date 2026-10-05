import type {
  ApplicationEventView,
  ConnectionState,
  JsonValue,
  ProposalView,
} from "./types";

export const FIELD_SERVICE_OUTCOME_NOTE =
  "Onsite field-service work order registered. This is not proof of repair.";

export const STALE_PROPOSAL_NOTE =
  "Approval was recorded, but fresh authoritative conditions no longer allowed execution. No field-service action was created.";

function stringValue(
  payload: Record<string, JsonValue>,
  key: string,
): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export function eventSummary(event: ApplicationEventView): string {
  const payload = event.payload;
  switch (event.event_type) {
    case "simulation.started":
      return "Run started";
    case "external.signal":
      return "Incident signal received";
    case "observation.recorded": {
      const sourceType = stringValue(payload, "source_type");
      return sourceType
        ? `Observation recorded: ${sourceType}`
        : "Observation recorded";
    }
    case "tool.started": {
      const tool = stringValue(payload, "tool_name");
      return tool ? `Tool started: ${tool}` : "Tool started";
    }
    case "tool.finished":
      return "Tool finished";
    case "finding.recorded":
      return "Finding recorded";
    case "proposal.created":
      return "Field visit proposal created";
    case "approval.decided": {
      const decision = stringValue(payload, "decision");
      return decision
        ? `Human decision recorded: ${decision}`
        : "Human decision recorded";
    }
    case "action.executed":
      return "Field service action registered";
    case "run.status_changed": {
      const status = stringValue(payload, "status");
      return status ? `Run status changed → ${status}` : "Run status changed";
    }
    default:
      return event.event_type;
  }
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return (
    new Intl.DateTimeFormat("en-GB", {
      dateStyle: "medium",
      timeStyle: "medium",
      timeZone: "UTC",
    }).format(date) + " UTC"
  );
}

export function proposalTone(
  status: ProposalView["status"],
): "pending" | "rejected" | "stale" | "executed" | "neutral" {
  if (status === "PENDING_APPROVAL") return "pending";
  if (status === "REJECTED") return "rejected";
  if (status === "STALE") return "stale";
  if (status === "EXECUTED") return "executed";
  return "neutral";
}

export function connectionTone(
  state: ConnectionState,
): "live" | "waiting" | "offline" {
  if (state === "Live") return "live";
  if (state === "Reconnecting") return "waiting";
  return "offline";
}
