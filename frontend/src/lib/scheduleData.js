// Static schedule data derived from the live API reference
// This serves as the pre-beta data source

import { format, addDays, parseISO, isAfter, isBefore, isEqual, getDay } from 'date-fns';

const RAW_SHIFTS = [
  // May 18 - fully open
  { date: "2026-05-18", label: "AM", attendant: { name: "OPEN ATTENDANT", status: "OPEN" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Attendant" },
  { date: "2026-05-18", label: "PM", attendant: { name: "OPEN ATTENDANT", status: "OPEN" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Attendant" },
  // May 19
  { date: "2026-05-19", label: "AM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  { date: "2026-05-19", label: "PM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // May 20
  { date: "2026-05-20", label: "AM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  { date: "2026-05-20", label: "PM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  // May 21
  { date: "2026-05-21", label: "AM", attendant: { name: "Nikki Meeks", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  { date: "2026-05-21", label: "PM", attendant: { name: "Nikki Meeks", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // May 22
  { date: "2026-05-22", label: "AM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  { date: "2026-05-22", label: "PM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Sidney DuBois", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // May 23 - Anna + Volunteer Crew Driver
  { date: "2026-05-23", label: "AM", attendant: { name: "Anna Squires", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-05-23", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Open Attendant" },
  // May 24
  { date: "2026-05-24", label: "AM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  { date: "2026-05-24", label: "PM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // May 25
  { date: "2026-05-25", label: "AM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Attendant" },
  { date: "2026-05-25", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Sidney DuBois", status: "ASSIGNED", cert: "EMT" }, crew_status: "Open Attendant" },
  // May 26
  { date: "2026-05-26", label: "AM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  { date: "2026-05-26", label: "PM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Sidney DuBois", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // May 27
  { date: "2026-05-27", label: "AM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  { date: "2026-05-27", label: "PM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // May 28
  { date: "2026-05-28", label: "AM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  { date: "2026-05-28", label: "PM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // May 29
  { date: "2026-05-29", label: "AM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Open Attendant" },
  { date: "2026-05-29", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Open Attendant" },
  // May 30
  { date: "2026-05-30", label: "AM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  { date: "2026-05-30", label: "PM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  // May 31
  { date: "2026-05-31", label: "AM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  { date: "2026-05-31", label: "PM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 1 - Career Fire starts (Mon)
  { date: "2026-06-01", label: "AM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-06-01", label: "PM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Needs Supervisor Review", supervisor_review: true },
  // Jun 2 (Tue)
  { date: "2026-06-02", label: "AM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Needs Supervisor Review", coverage_gap: "0600-0800", supervisor_review: true },
  { date: "2026-06-02", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Needs Supervisor Review", supervisor_review: true },
  // Jun 3 (Wed - no career fire)
  { date: "2026-06-03", label: "AM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  { date: "2026-06-03", label: "PM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  // Jun 4 (Thu)
  { date: "2026-06-04", label: "AM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-06-04", label: "PM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  // Jun 5
  { date: "2026-06-05", label: "AM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  { date: "2026-06-05", label: "PM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 6
  { date: "2026-06-06", label: "AM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Open Attendant" },
  { date: "2026-06-06", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Open Attendant" },
  // Jun 7
  { date: "2026-06-07", label: "AM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Open Attendant" },
  { date: "2026-06-07", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Attendant" },
  // Jun 8 (Mon)
  { date: "2026-06-08", label: "AM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-06-08", label: "PM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 9 (Tue)
  { date: "2026-06-09", label: "AM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-06-09", label: "PM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 10 (Wed)
  { date: "2026-06-10", label: "AM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Attendant" },
  { date: "2026-06-10", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Attendant" },
  // Jun 11 (Thu)
  { date: "2026-06-11", label: "AM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-06-11", label: "PM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  // Jun 12
  { date: "2026-06-12", label: "AM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  { date: "2026-06-12", label: "PM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 13
  { date: "2026-06-13", label: "AM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  { date: "2026-06-13", label: "PM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  // Jun 14
  { date: "2026-06-14", label: "AM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Open Attendant" },
  { date: "2026-06-14", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Attendant" },
  // Jun 15 (Mon)
  { date: "2026-06-15", label: "AM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-06-15", label: "PM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 16 (Tue)
  { date: "2026-06-16", label: "AM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Open Attendant", coverage_gap: "0600-0800" },
  { date: "2026-06-16", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Sidney DuBois", status: "ASSIGNED", cert: "EMT" }, crew_status: "Open Attendant" },
  // Jun 17 (Wed)
  { date: "2026-06-17", label: "AM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  { date: "2026-06-17", label: "PM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 18 (Thu)
  { date: "2026-06-18", label: "AM", attendant: { name: "Nikki Meeks", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-06-18", label: "PM", attendant: { name: "Nikki Meeks", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  // Jun 19 (Fri)
  { date: "2026-06-19", label: "AM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  { date: "2026-06-19", label: "PM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Sidney DuBois", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 20
  { date: "2026-06-20", label: "AM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  { date: "2026-06-20", label: "PM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  // Jun 21
  { date: "2026-06-21", label: "AM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  { date: "2026-06-21", label: "PM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 22 (Mon)
  { date: "2026-06-22", label: "AM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Open Attendant", coverage_gap: "0600-0800" },
  { date: "2026-06-22", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Attendant" },
  // Jun 23 (Tue)
  { date: "2026-06-23", label: "AM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-06-23", label: "PM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 24 (Wed)
  { date: "2026-06-24", label: "AM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Driver" },
  { date: "2026-06-24", label: "PM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Sidney DuBois", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 25 (Thu)
  { date: "2026-06-25", label: "AM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-06-25", label: "PM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 26 (Fri)
  { date: "2026-06-26", label: "AM", attendant: { name: "Nikki Meeks", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  { date: "2026-06-26", label: "PM", attendant: { name: "Nikki Meeks", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Sidney DuBois", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 27
  { date: "2026-06-27", label: "AM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  { date: "2026-06-27", label: "PM", attendant: { name: "Lynnsey Benson", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  // Jun 28
  { date: "2026-06-28", label: "AM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Volunteer Crew Driver", status: "STRUCTURAL" }, crew_status: "Complete" },
  { date: "2026-06-28", label: "PM", attendant: { name: "Barbara", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Brian Ennis", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 29 (Mon)
  { date: "2026-06-29", label: "AM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Complete", coverage_gap: "0600-0800" },
  { date: "2026-06-29", label: "PM", attendant: { name: "Sophia Williams", status: "ASSIGNED", cert: "AEMT" }, driver: { name: "Collin Harrison", status: "ASSIGNED", cert: "EMT" }, crew_status: "Complete" },
  // Jun 30 (Tue - last day of frozen horizon)
  { date: "2026-06-30", label: "AM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "Career Fire Driver", status: "STRUCTURAL", structural_time: "0800-1800" }, crew_status: "Open Attendant", coverage_gap: "0600-0800" },
  { date: "2026-06-30", label: "PM", attendant: { name: "OPEN ALS", status: "OPEN" }, driver: { name: "OPEN DRIVER", status: "OPEN" }, crew_status: "Open Attendant" },
];

export function getScheduleData() {
  const currentYear = new Date().getFullYear();
  const wrongYear = RAW_SHIFTS.find(s => !s.date.startsWith(String(currentYear)));
  if (wrongYear) {
    console.warn(`[ShiftCommander] ⚠️ Schedule data contains dates outside ${currentYear} (e.g. ${wrongYear.date}). Update RAW_SHIFTS in scheduleData.js.`);
  }
  return RAW_SHIFTS;
}

export function getShiftsForDateRange(startDate, endDate) {
  return RAW_SHIFTS.filter(s => {
    const d = parseISO(s.date);
    return (isAfter(d, parseISO(startDate)) || isEqual(d, parseISO(startDate))) &&
           (isBefore(d, parseISO(endDate)) || isEqual(d, parseISO(endDate)));
  });
}

export function groupShiftsByDate(shifts) {
  const grouped = {};
  shifts.forEach(shift => {
    if (!grouped[shift.date]) {
      grouped[shift.date] = { date: shift.date, am: null, pm: null };
    }
    if (shift.label === "AM") grouped[shift.date].am = shift;
    if (shift.label === "PM") grouped[shift.date].pm = shift;
  });
  return Object.values(grouped).sort((a, b) => a.date.localeCompare(b.date));
}

// Re-exported from shiftDisplayRules for backward compatibility.
// Always import from shiftDisplayRules directly in new code.
export { getCrewStatusType } from './shiftDisplayRules';

export function isOpenSeat(status) {
  return status === 'OPEN';
}

export function isStructuralCoverage(status) {
  return status === 'STRUCTURAL';
}

export const MEMBERS = [
  { id: "180", name: "Sophia Williams", cert: "AEMT", canDrive: false },
  { id: "188", name: "Brian Ennis", cert: "EMT", canDrive: true },
  { id: "190", name: "Lynnsey Benson", cert: "AEMT", canDrive: false },
  { id: "191", name: "Nikki Meeks", cert: "AEMT", canDrive: false },
  { id: "192", name: "Barbara", cert: "AEMT", canDrive: false },
  { id: "193", name: "Collin Harrison", cert: "EMT", canDrive: true },
  { id: "194", name: "Sidney DuBois", cert: "EMT", canDrive: true },
  { id: "195", name: "Anna Squires", cert: "AEMT", canDrive: false },
  { id: "107", name: "Gracie Toney", cert: "ALS", canDrive: true },
];