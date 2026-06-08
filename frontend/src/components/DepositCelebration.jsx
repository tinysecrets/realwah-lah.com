/**
 * DepositCelebration.jsx — a fire-and-forget overlay that fires on Deposit click.
 * Genie zooms in, coins burst, sparkles trail, "WAH-LAH!" banner pops.
 * Pure CSS animations; unmounts itself after ~2.2s.
 */
import React, { useEffect, useState } from "react";

const COIN_COUNT = 18;

const DepositCelebration = ({ onDone }) => {
  const [gone, setGone] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      setGone(true);
      onDone && onDone();
    }, 2200);
    return () => clearTimeout(t);
  }, [onDone]);

  if (gone) return null;

  return (
    <div className="dep-celebration" aria-hidden="true" data-testid="deposit-celebration">
      <div className="dep-banner">
        <span className="dep-banner-text">WAH-LAH!</span>
      </div>
      <img
        className="dep-genie"
        src="/mascots/genie_pointing.png"
        alt=""
        onError={(e) => { e.target.style.display = "none"; }}
      />
      <div className="dep-coins">
        {Array.from({ length: COIN_COUNT }).map((_, i) => (
          <span
            key={i}
            className="dep-coin"
            style={{
              "--angle": `${(360 / COIN_COUNT) * i}deg`,
              "--delay": `${(i % 6) * 40}ms`,
              "--dist": `${220 + (i % 5) * 40}px`,
            }}
          />
        ))}
      </div>
      <div className="dep-sparkles">
        {Array.from({ length: 26 }).map((_, i) => (
          <span
            key={i}
            className="dep-spark"
            style={{
              left: `${Math.random() * 100}%`,
              top: `${40 + Math.random() * 40}%`,
              animationDelay: `${Math.random() * 600}ms`,
            }}
          />
        ))}
      </div>
    </div>
  );
};

export default DepositCelebration;
