"use client";

import { useState } from 'react';
import { motion } from 'motion/react';
import { Zap, Check, X } from 'lucide-react';

interface Employee { id: string; name: string; avatar: string; role: string; }
interface Shift { id: string; employeeId: string; day: number; startHour: number; endHour: number; role: string; color: string; }

function shiftDuration(s: Shift) {
  return s.endHour > s.startHour ? s.endHour - s.startHour : 24 - s.startHour + s.endHour;
}

interface PublishWeekModalProps {
  weekLabel: string;
  shifts: Shift[];
  employees: Employee[];
  dark?: boolean;
  onClose: () => void;
  onComplete: () => void;
}

export function PublishWeekModal({ weekLabel, shifts, employees, dark = false, onClose, onComplete }: PublishWeekModalProps) {
  const [stage, setStage] = useState<'confirm' | 'publishing' | 'success'>('confirm');
  const [progress, setProgress] = useState(0);
  const [notifiedEmployees, setNotifiedEmployees] = useState<string[]>([]);

  const affectedEmployees = Array.from(new Set(shifts.map(s => s.employeeId)))
    .map(id => employees.find(e => e.id === id))
    .filter(Boolean) as Employee[];

  const totalShifts = shifts.length;
  const totalHours = shifts.reduce((sum, s) => sum + shiftDuration(s), 0);
  const modalClass = dark ? 'bg-[#0F2E4C] border border-white/[0.08]' : 'bg-white border border-[#E5E7EB]';
  const borderClass = dark ? 'border-white/[0.08]' : 'border-[#F0F0F5]';
  const textPrimary = dark ? 'text-white' : 'text-[#0A2540]';
  const textSecondary = dark ? 'text-[#C1CED8]' : 'text-[#8898AA]';
  const metricCardClass = dark ? 'bg-white/[0.04] border border-white/[0.08]' : 'bg-[#F7F8FA] border border-[#E5E7EB]';
  const subtleSurfaceClass = dark ? 'bg-white/[0.03]' : 'bg-[#F7F8FA]/50';
  const rowSurfaceClass = dark ? 'bg-white/[0.03] border border-white/[0.08]' : 'bg-white border border-[#E5E7EB]';
  const closeButtonClass = dark ? 'p-1.5 rounded-lg hover:bg-white/[0.06] transition-colors' : 'p-1.5 rounded-lg hover:bg-[#F7F8FA] transition-colors';
  const progressTrackClass = dark ? 'bg-white/[0.08]' : 'bg-[#F0F0F5]';
  const footerButtonClass = dark
    ? 'flex-1 py-2.5 rounded-xl border border-white/[0.08] text-[12px] text-[#C1CED8] hover:bg-white/[0.04] transition-colors'
    : 'flex-1 py-2.5 rounded-xl border border-[#E5E7EB] text-[12px] text-[#5E6D7A] hover:bg-[#F7F8FA] transition-colors';

  const handlePublish = () => {
    setStage('publishing');
    setProgress(0);

    const totalSteps = Math.max(affectedEmployees.length, 1);
    const stepDuration = 2000 / totalSteps;

    if (affectedEmployees.length === 0) {
      setProgress(100);
      setTimeout(() => {
        setStage('success');
        setTimeout(() => {
          onComplete();
        }, 1500);
      }, 300);
      return;
    }

    affectedEmployees.forEach((emp, idx) => {
      setTimeout(() => {
        setNotifiedEmployees(prev => [...prev, emp.id]);
        setProgress(((idx + 1) / totalSteps) * 100);

        if (idx === totalSteps - 1) {
          setTimeout(() => {
            setStage('success');
            setTimeout(() => {
              onComplete();
            }, 1500);
          }, 300);
        }
      }, stepDuration * idx);
    });
  };

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black z-40" onClick={stage === 'confirm' ? onClose : undefined} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[90vw] max-w-[520px] rounded-2xl shadow-2xl overflow-hidden ${modalClass}`}>

        <div className={`px-6 py-5 border-b flex items-center justify-between ${borderClass}`}>
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
              stage === 'success' ? 'bg-[#00B893]/10' : 'bg-gradient-to-br from-[#635BFF] to-[#8B5CF6]'
            }`}>
              {stage === 'success' ? (
                <Check size={20} className="text-[#00B893]" />
              ) : (
                <Zap size={20} className="text-white" />
              )}
            </div>
            <div>
              <h3 className={`text-[17px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                {stage === 'confirm' && 'Publish Schedule'}
                {stage === 'publishing' && 'Publishing...'}
                {stage === 'success' && 'Schedule Published!'}
              </h3>
              <p className={`text-[11px] mt-0.5 ${textSecondary}`} style={{ fontWeight: 440 }}>
                {stage === 'confirm' && `${weekLabel}`}
                {stage === 'publishing' && `Notifying ${affectedEmployees.length} staff members`}
                {stage === 'success' && 'All notifications sent successfully'}
              </p>
            </div>
          </div>
          {stage === 'confirm' && (
            <button onClick={onClose} className={closeButtonClass}>
              <X size={18} className={textSecondary} />
            </button>
          )}
        </div>

        <div className="px-6 py-5">
          {stage === 'confirm' && (
            <>
              <div className="grid grid-cols-3 gap-3 mb-5">
                <div className={`px-4 py-3 rounded-xl ${metricCardClass}`}>
                  <p className={`text-[10px] uppercase tracking-[0.05em] ${textSecondary}`} style={{ fontWeight: 500 }}>Shifts</p>
                  <p className={`text-[20px] mt-1 ${textPrimary}`} style={{ fontWeight: 620 }}>{totalShifts}</p>
                </div>
                <div className={`px-4 py-3 rounded-xl ${metricCardClass}`}>
                  <p className={`text-[10px] uppercase tracking-[0.05em] ${textSecondary}`} style={{ fontWeight: 500 }}>Staff</p>
                  <p className={`text-[20px] mt-1 ${textPrimary}`} style={{ fontWeight: 620 }}>{affectedEmployees.length}</p>
                </div>
                <div className={`px-4 py-3 rounded-xl ${metricCardClass}`}>
                  <p className={`text-[10px] uppercase tracking-[0.05em] ${textSecondary}`} style={{ fontWeight: 500 }}>Hours</p>
                  <p className={`text-[20px] mt-1 ${textPrimary}`} style={{ fontWeight: 620 }}>{totalHours}</p>
                </div>
              </div>

              <div className="space-y-3 mb-5">
                <p className={`text-[11px] uppercase tracking-[0.05em] ${textSecondary}`} style={{ fontWeight: 500 }}>What will happen</p>
                <div className="space-y-2">
                  {[
                    { icon: '📧', text: 'Email notifications sent to all staff', detail: `${affectedEmployees.length} recipients` },
                    { icon: '📱', text: 'Push notifications via Backfill mobile app', detail: 'Instant delivery' },
                    { icon: '📅', text: 'Shifts added to employee calendars', detail: 'Auto-sync enabled' },
                  ].map((item, idx) => (
                    <div key={idx} className={`flex items-start gap-3 p-3 rounded-lg ${subtleSurfaceClass}`}>
                      <span className="text-[18px]">{item.icon}</span>
                      <div className="flex-1">
                        <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 500 }}>{item.text}</p>
                        <p className={`text-[10px] mt-0.5 ${textSecondary}`} style={{ fontWeight: 420 }}>{item.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <p className={`text-[11px] uppercase tracking-[0.05em] mb-3 ${textSecondary}`} style={{ fontWeight: 500 }}>Staff receiving notifications</p>
                <div className="max-h-[180px] overflow-y-auto space-y-1.5 pr-1">
                  {affectedEmployees.map(emp => {
                    const empShifts = shifts.filter(s => s.employeeId === emp.id);
                    const empHours = empShifts.reduce((sum, s) => sum + shiftDuration(s), 0);
                    return (
                      <div key={emp.id} className={`flex items-center gap-3 p-2.5 rounded-lg ${rowSurfaceClass}`}>
                        <img src={emp.avatar} alt={emp.name} className={`w-8 h-8 rounded-full object-cover shrink-0 ring-1 ${dark ? 'ring-white/[0.08]' : 'ring-[#E5E7EB]'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-[12px] truncate ${textPrimary}`} style={{ fontWeight: 500 }}>{emp.name}</p>
                          <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>{emp.role}</p>
                        </div>
                        <div className="text-right">
                          <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 540 }}>{empShifts.length} shifts</p>
                          <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 420 }}>{empHours}h</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {stage === 'publishing' && (
            <div className="py-6">
              <div className="mb-6">
                <div className="flex items-center justify-between mb-2">
                  <p className={`text-[11px] uppercase tracking-[0.05em] ${textSecondary}`} style={{ fontWeight: 500 }}>Publishing progress</p>
                  <p className="text-[12px] text-[#635BFF]" style={{ fontWeight: 540 }}>{Math.round(progress)}%</p>
                </div>
                <div className={`h-2 rounded-full overflow-hidden ${progressTrackClass}`}>
                  <motion.div
                    className="h-full rounded-full bg-gradient-to-r from-[#635BFF] to-[#8B5CF6]"
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <p className={`text-[11px] uppercase tracking-[0.05em] mb-3 ${textSecondary}`} style={{ fontWeight: 500 }}>Notifying staff</p>
                <div className="max-h-[240px] overflow-y-auto space-y-1.5 pr-1">
                  {affectedEmployees.map((emp, idx) => {
                    const isNotified = notifiedEmployees.includes(emp.id);
                    const isCurrent = notifiedEmployees.length === idx;
                    return (
                      <motion.div
                        key={emp.id}
                        initial={{ opacity: 0.4 }}
                        animate={{ opacity: isNotified || isCurrent ? 1 : 0.4 }}
                        className={`flex items-center gap-3 p-2.5 rounded-lg transition-all ${
                          isNotified ? 'bg-[#00B893]/[0.06] border border-[#00B893]/20' :
                          isCurrent ? 'bg-[#635BFF]/[0.06] border border-[#635BFF]/20' :
                          dark ? 'bg-white/[0.04] border border-white/[0.08]' : 'bg-[#F7F8FA] border border-[#E5E7EB]'
                        }`}>
                        <img src={emp.avatar} alt={emp.name} className="w-7 h-7 rounded-full object-cover shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className={`text-[11px] truncate ${textPrimary}`} style={{ fontWeight: 500 }}>{emp.name}</p>
                          <p className={`text-[9px] ${textSecondary}`} style={{ fontWeight: 420 }}>{emp.role}</p>
                        </div>
                        {isNotified && (
                          <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 400, damping: 15 }}
                            className="w-5 h-5 rounded-full bg-[#00B893] flex items-center justify-center">
                            <Check size={11} className="text-white" />
                          </motion.div>
                        )}
                        {isCurrent && (
                          <div className="flex items-center gap-1">
                            <div className="w-1 h-1 rounded-full bg-[#635BFF] animate-pulse" />
                            <div className="w-1 h-1 rounded-full bg-[#635BFF] animate-pulse" style={{ animationDelay: '150ms' }} />
                            <div className="w-1 h-1 rounded-full bg-[#635BFF] animate-pulse" style={{ animationDelay: '300ms' }} />
                          </div>
                        )}
                      </motion.div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {stage === 'success' && (
            <div className="py-8 text-center">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: 'spring', stiffness: 200, damping: 15 }}
                className="w-16 h-16 mx-auto mb-4 rounded-full bg-[#00B893]/10 flex items-center justify-center">
                <Check size={32} className="text-[#00B893]" />
              </motion.div>
              <h4 className={`text-[16px] mb-2 ${textPrimary}`} style={{ fontWeight: 620 }}>All Set!</h4>
              <p className={`text-[12px] mb-4 ${textSecondary}`} style={{ fontWeight: 440 }}>
                {totalShifts} shifts published to {affectedEmployees.length} staff members
              </p>
              <div className="flex items-center justify-center gap-6 pt-4">
                <div className="text-center">
                  <p className="text-[24px] text-[#635BFF]" style={{ fontWeight: 620 }}>📧</p>
                  <p className={`text-[10px] mt-1 ${textSecondary}`} style={{ fontWeight: 440 }}>Emails sent</p>
                </div>
                <div className="text-center">
                  <p className="text-[24px] text-[#635BFF]" style={{ fontWeight: 620 }}>📱</p>
                  <p className={`text-[10px] mt-1 ${textSecondary}`} style={{ fontWeight: 440 }}>Push sent</p>
                </div>
                <div className="text-center">
                  <p className="text-[24px] text-[#635BFF]" style={{ fontWeight: 620 }}>📅</p>
                  <p className={`text-[10px] mt-1 ${textSecondary}`} style={{ fontWeight: 440 }}>Calendars synced</p>
                </div>
              </div>
            </div>
          )}
        </div>

        {stage === 'confirm' && (
          <div className={`px-6 py-4 border-t flex gap-2.5 ${borderClass}`}>
            <button onClick={onClose}
              className={footerButtonClass}
              style={{ fontWeight: 500 }}>
              Cancel
            </button>
            <motion.button
              whileTap={{ scale: 0.97 }}
              onClick={handlePublish}
              className="flex-1 py-2.5 rounded-xl text-[12px] text-white transition-all hover:shadow-[0_0_20px_rgba(99,91,255,0.3)] flex items-center justify-center gap-2"
              style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
              <Zap size={13} />
              Publish & Notify
            </motion.button>
          </div>
        )}
      </motion.div>
    </>
  );
}
