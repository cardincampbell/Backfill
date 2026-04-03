"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";

function TypingIndicator({ dark = false }: { dark?: boolean }) {
  return (
    <div className="flex items-center gap-[5px] px-1 py-0.5">
      {[0, 0.15, 0.3].map((delay, i) => (
        <motion.div
          key={i}
          className={`w-[7px] h-[7px] rounded-full ${dark ? 'bg-white/60' : 'bg-[#86868b]'}`}
          animate={{ opacity: [0.3, 1, 0.3], scale: [0.85, 1, 0.85] }}
          transition={{ duration: 0.9, repeat: Infinity, delay }}
        />
      ))}
    </div>
  );
}

export function LandingPhoneMockup() {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const timers = [
      setTimeout(() => setStage(1), 800),
      setTimeout(() => setStage(2), 2400),
      setTimeout(() => setStage(3), 3200),
      setTimeout(() => setStage(4), 4800),
      setTimeout(() => setStage(5), 5400),
      setTimeout(() => setStage(6), 6800),
      setTimeout(() => setStage(7), 7600),
      setTimeout(() => setStage(8), 9200),
    ];
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="relative w-full max-w-[280px] sm:max-w-[340px] lg:max-w-[380px] mx-auto">
      {/* iPhone 15 Pro Frame — precise titanium gradient */}
      <div
        className="relative rounded-[56px] p-[3px]"
        style={{
          background: 'linear-gradient(135deg, #d4d4d6 0%, #a1a1a3 20%, #6e6e73 40%, #48484a 50%, #6e6e73 60%, #a1a1a3 80%, #d4d4d6 100%)',
          boxShadow: '0 0 0 1.5px rgba(0,0,0,0.12), 0 30px 90px rgba(0,0,0,0.50), 0 12px 35px rgba(0,0,0,0.30)',
        }}
      >
        {/* Inner titanium bezel */}
        <div
          className="rounded-[54px] p-[8px]"
          style={{ 
            background: 'linear-gradient(145deg, #3a3a3c 0%, #2c2c2e 30%, #1c1c1e 50%, #2c2c2e 70%, #3a3a3c 100%)',
          }}
        >
          {/* Screen */}
          <div className="bg-[#f2f2f7] rounded-[46px] overflow-hidden relative flex flex-col" style={{ aspectRatio: '393/852' }}>
            {/* Status Bar */}
            <div className="relative z-20 px-[33px] pt-[15px] pb-0 flex items-center justify-between bg-[#f2f2f7]">
              <span className="text-[15px] tracking-[-0.02em] text-black" style={{ fontWeight: 590, letterSpacing: '-0.3px' }}>9:41</span>
              <div className="flex items-center gap-[6px]">
                {/* Cellular - 4 bars */}
                <svg width="18" height="12" viewBox="0 0 18 12" fill="none">
                  <rect x="0" y="7" width="3.5" height="5" rx="1" fill="black" />
                  <rect x="4.8" y="4.5" width="3.5" height="7.5" rx="1" fill="black" />
                  <rect x="9.6" y="2" width="3.5" height="10" rx="1" fill="black" />
                  <rect x="14.4" y="0" width="3.5" height="12" rx="1" fill="black" />
                </svg>
                {/* WiFi */}
                <svg width="17" height="12" viewBox="0 0 17 12" fill="none">
                  <path d="M8.5 10a1.5 1.5 0 100 2 1.5 1.5 0 000-2z" fill="black" />
                  <path d="M5 7.5a5 5 0 017 0" stroke="black" strokeWidth="1.5" strokeLinecap="round" />
                  <path d="M2 5a8.5 8.5 0 0113 0" stroke="black" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                {/* Battery */}
                <svg width="27" height="13" viewBox="0 0 27 13" fill="none">
                  <rect x="0.5" y="0.5" width="22" height="12" rx="2.8" stroke="black" strokeOpacity="0.35" />
                  <path d="M24 4.2a1.8 1.8 0 011 1.6v1.4a1.8 1.8 0 01-1 1.6" stroke="black" strokeOpacity="0.4" strokeWidth="1" strokeLinecap="round" />
                  <rect x="2" y="2" width="19" height="9" rx="1.5" fill="black" />
                </svg>
              </div>
            </div>

            {/* Dynamic Island - more precise sizing and positioning */}
            <div className="absolute top-[13px] left-1/2 -translate-x-1/2 w-[126px] h-[37px] bg-black rounded-[22px] z-30" 
              style={{ 
                boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
              }} 
            />

            {/* iMessage Navigation Bar */}
            <div className="bg-[#f2f2f7] px-[18px] pt-[6px] pb-[9px]">
              <div className="flex items-center justify-between">
                {/* Back chevron in circle - iOS 26 style */}
                <button className="flex items-center justify-center w-[34px] h-[34px] rounded-full bg-[#e8e8ed] -ml-1">
                  <svg width="10" height="17" viewBox="0 0 10 17" fill="none">
                    <path d="M9 1.5L2 8.5L9 15.5" stroke="#007AFF" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                <div className="flex-1" />
                {/* Video call icon */}
                <button className="flex items-center justify-center w-[34px] h-[34px] rounded-full bg-[#e8e8ed]">
                  <svg width="20" height="14" viewBox="0 0 20 14" fill="none">
                    <rect x="1" y="2" width="12" height="10" rx="2.5" stroke="#007AFF" strokeWidth="1.8" />
                    <path d="M14 5.5l4.5-2.5v8L14 8.5v-3z" fill="#007AFF" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Contact header */}
            <div className="bg-[#f2f2f7] pb-[14px] flex flex-col items-center border-b border-[#d1d1d6]/70">
              {/* Avatar */}
              <div className="w-[56px] h-[56px] rounded-full bg-gradient-to-br from-[#9e9ea4] to-[#6e6e73] flex items-center justify-center mb-[5px]"
                style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}
              >
                <span className="text-white text-[24px]" style={{ fontWeight: 510 }}>B</span>
              </div>
              <div className="text-[15px] text-black tracking-[-0.02em] mb-[1px]" style={{ fontWeight: 600 }}>1-800-BACKFILL</div>
            </div>

            {/* Messages Area */}
            <div className="px-[14px] pt-[16px] pb-2 space-y-[7px] flex-1 overflow-hidden bg-white">
              <AnimatePresence mode="popLayout">
                {/* Timestamp */}
                <motion.div
                  key="time-header"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-center pb-[6px]"
                >
                  <span className="text-[12px] text-[#8e8e93]" style={{ fontWeight: 400 }}>Today 5:47 AM</span>
                </motion.div>

                {/* Employee typing */}
                {stage === 1 && (
                  <motion.div
                    key="emp-typing"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="flex justify-end"
                  >
                    <div className="bg-[#007AFF] px-[15px] py-[9px] rounded-[18px]" 
                      style={{ borderBottomRightRadius: '4px' }}
                    >
                      <TypingIndicator dark />
                    </div>
                  </motion.div>
                )}

                {/* Employee message */}
                {stage >= 2 && (
                  <motion.div
                    key="emp-msg"
                    initial={{ opacity: 0, scale: 0.92, y: 8 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                    className="flex justify-end"
                  >
                    <div className="bg-[#007AFF] text-white px-[15px] py-[8px] rounded-[18px] max-w-[75%]" 
                      style={{ borderBottomRightRadius: '4px' }}
                    >
                      <p className="text-[17px] leading-[1.35]" style={{ fontWeight: 400, letterSpacing: '-0.3px' }}>Hey, I'm not feeling well. Can't make my shift tonight at 6.</p>
                    </div>
                  </motion.div>
                )}

                {/* Agent typing 1 */}
                {stage === 3 && (
                  <motion.div
                    key="agent-typing-1"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="flex justify-start"
                  >
                    <div className="bg-[#e9e9eb] px-[15px] py-[9px] rounded-[18px]" 
                      style={{ borderBottomLeftRadius: '4px' }}
                    >
                      <TypingIndicator />
                    </div>
                  </motion.div>
                )}

                {/* Agent response 1 */}
                {stage >= 4 && (
                  <motion.div
                    key="agent-msg-1"
                    initial={{ opacity: 0, scale: 0.92, y: 8 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                    className="flex justify-start"
                  >
                    <div className="bg-[#e9e9eb] text-black px-[15px] py-[8px] rounded-[18px] max-w-[75%]" 
                      style={{ borderBottomLeftRadius: '4px' }}
                    >
                      <p className="text-[17px] leading-[1.35]" style={{ fontWeight: 400, letterSpacing: '-0.3px' }}>No worries! I'll start reaching out to find coverage for your 6 PM shift right now.</p>
                    </div>
                  </motion.div>
                )}

                {/* Agent typing 2 */}
                {stage === 5 && (
                  <motion.div
                    key="agent-typing-2"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="flex justify-start"
                  >
                    <div className="bg-[#e9e9eb] px-[15px] py-[9px] rounded-[18px]" 
                      style={{ borderBottomLeftRadius: '4px' }}
                    >
                      <TypingIndicator />
                    </div>
                  </motion.div>
                )}

                {/* Agent response 2 */}
                {stage >= 6 && (
                  <motion.div
                    key="agent-msg-2"
                    initial={{ opacity: 0, scale: 0.92, y: 8 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                    className="flex justify-start"
                  >
                    <div className="bg-[#e9e9eb] text-black px-[15px] py-[8px] rounded-[18px] max-w-[75%]" 
                      style={{ borderBottomLeftRadius: '4px' }}
                    >
                      <p className="text-[17px] leading-[1.35]" style={{ fontWeight: 400, letterSpacing: '-0.3px' }}>Done — Marcus confirmed. He'll cover your 6–close tonight. You're all set.</p>
                    </div>
                  </motion.div>
                )}

                {/* Employee typing 2 */}
                {stage === 7 && (
                  <motion.div
                    key="emp-typing-2"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="flex justify-end"
                  >
                    <div className="bg-[#007AFF] px-[15px] py-[9px] rounded-[18px]" 
                      style={{ borderBottomRightRadius: '4px' }}
                    >
                      <TypingIndicator dark />
                    </div>
                  </motion.div>
                )}

                {/* Employee response 2 */}
                {stage >= 8 && (
                  <motion.div
                    key="emp-msg-2"
                    initial={{ opacity: 0, scale: 0.92, y: 8 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                    className="flex justify-end"
                  >
                    <div className="bg-[#007AFF] text-white px-[15px] py-[8px] rounded-[18px] max-w-[75%]" 
                      style={{ borderBottomRightRadius: '4px' }}
                    >
                      <p className="text-[17px] leading-[1.35]" style={{ fontWeight: 400, letterSpacing: '-0.3px' }}>That was fast, thank you!</p>
                    </div>
                  </motion.div>
                )}

                {/* Delivered indicator */}
                {stage >= 8 && (
                  <motion.div
                    key="delivered"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.4 }}
                    className="flex justify-end pr-[2px] pt-[2px]"
                  >
                    <span className="text-[12px] text-[#8e8e93]" style={{ fontWeight: 400 }}>Delivered</span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* iMessage Input Bar */}
            <div className="bg-[#f7f7f7] px-[14px] pt-[7px] pb-[6px] border-t border-[#d1d1d6]/50">
              <div className="flex items-end gap-[10px]">
                {/* Plus button */}
                <button className="flex-shrink-0 w-[32px] h-[32px] rounded-full bg-[#007AFF] flex items-center justify-center mb-[1px]">
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                    <path d="M9 3v12M3 9h12" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
                  </svg>
                </button>

                {/* Text field */}
                <div className="flex-1 bg-white rounded-[20px] border border-[#d1d1d6]/80 px-[14px] py-[7px] flex items-center min-h-[36px]">
                  <span className="text-[17px] text-[#3c3c43]/30 flex-1" style={{ fontWeight: 400 }}>iMessage</span>
                  {/* Mic icon */}
                  <svg width="16" height="21" viewBox="0 0 16 21" fill="none" className="flex-shrink-0 opacity-50">
                    <rect x="4.5" y="1" width="7" height="11" rx="3.5" stroke="#3c3c43" strokeWidth="1.5" />
                    <path d="M1 10a7 7 0 0014 0" stroke="#3c3c43" strokeWidth="1.5" strokeLinecap="round" />
                    <path d="M8 18v2.5" stroke="#3c3c43" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </div>
              </div>
            </div>

            {/* Home Indicator */}
            <div className="pb-[10px] pt-[8px] flex justify-center bg-[#f7f7f7]">
              <div className="w-[140px] h-[5px] bg-black/25 rounded-full" />
            </div>
          </div>
        </div>
      </div>

      {/* Ambient glow behind phone */}
      <div className="absolute inset-0 -z-10 scale-110 bg-gradient-to-br from-[#635BFF]/20 via-[#0070F3]/10 to-[#00C7B7]/15 blur-[50px] opacity-60 rounded-full" />
    </div>
  );
}
