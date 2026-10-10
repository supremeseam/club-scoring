/**
 * Standard scoring codes and rule wording (Racing Rules of Sailing 2021-2024, Appendix A and the
 * rules cited). Used to pre-fill a penalty reason that the race committee can edit. Reasons are shown
 * publicly. Change the wording here to match your club's sailing instructions.
 */
export type StatusInfo = { label: string; note?: string; pct?: number; needsReason?: boolean };

export const STATUS_INFO: Record<string, StatusInfo> = {
  DNC: { label: "Did not come to the starting area" },
  DNS: { label: "Did not start (other than OCS, UFD, BFD)" },
  OCS: { label: "On the course side at the start", note: "On the course side of the starting line at her starting signal (RRS 29.1)", needsReason: true },
  DNF: { label: "Did not finish" },
  RET: { label: "Retired", note: "Retired (RRS 28.1 / 44.1)" },
  DSQ: { label: "Disqualified", needsReason: true },
  DNE: { label: "Disqualification not excludable (RRS 2, 30.3, 69 etc.)", needsReason: true },
  UFD: { label: "U flag disqualification", note: "U flag rule (RRS 30.3)", needsReason: true },
  BFD: { label: "Black flag disqualification", note: "Black flag rule (RRS 30.4)", needsReason: true },
  TLE: { label: "Finished after the time limit" },
  RDG: { label: "Redress given", note: "Redress given (RRS 60.1(b), A9)", needsReason: true },
  SCP: { label: "Scoring penalty", note: "Scoring Penalty taken (RRS 44.3)", pct: 20, needsReason: true },
  ZFP: { label: "Z flag penalty (20%)", note: "Z flag rule (RRS 30.2)", needsReason: true },
  RCD: { label: "Race committee duty" },
};

export const STATUS_CODES = Object.keys(STATUS_INFO);

/** Typing suggestions for the "rule" fields (free text is always allowed). */
export const RULE_SUGGESTIONS = [
  "RRS 10 On Opposite Tacks",
  "RRS 11 On the Same Tack, Overlapped",
  "RRS 12 On the Same Tack, Not Overlapped",
  "RRS 13 While Tacking",
  "RRS 14 Avoiding Contact",
  "RRS 15 Acquiring Right of Way",
  "RRS 16 Changing Course",
  "RRS 17 On the Same Tack; Proper Course",
  "RRS 18 Mark-Room",
  "RRS 19 Room to Pass an Obstruction",
  "RRS 20 Room to Tack at an Obstruction",
  "RRS 28 Sailing the Course",
  "RRS 29.1 Individual Recall",
  "RRS 30.2 Z Flag Rule",
  "RRS 30.3 U Flag Rule",
  "RRS 30.4 Black Flag Rule",
  "RRS 31 Touching a Mark",
  "RRS 41 Outside Help",
  "RRS 42 Propulsion",
  "RRS 44 Penalties at the Time of an Incident",
];
