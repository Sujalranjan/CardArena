import React, { useState } from 'react';
import { Check, ChevronDown, ChevronUp, Copy, ShieldCheck } from 'lucide-react';
import type { DeckDefinition, FairnessRecord } from '../types';
import { ApiService } from '../services/api';
import {
  SUPPORTED_ALGORITHM,
  handMatchesDeal,
  isWebCryptoAvailable,
  verifyFairnessRecord,
} from '../fairness/verify';
import type { DealtHandSnapshot, FairnessVerificationResult } from '../fairness/verify';

interface FairnessPanelProps {
  records: FairnessRecord[];
  currentRound: number;
  /** Dealt hand observed by this client for a round, if it was seen before any card left it. */
  getDealtHand?: (roundNumber: number) => DealtHandSnapshot | undefined;
  /** Source of documented canonical decks; defaults to the public backend endpoint. */
  loadDeckDefinition?: (name: string) => Promise<DeckDefinition>;
}

type VerifyState =
  | { status: 'running' }
  | { status: 'error'; message: string }
  | { status: 'done'; result: FairnessVerificationResult; handMatches: boolean | null };

const recordKey = (r: FairnessRecord) => `${r.game_id}:${r.round_number}`;

const CopyableValue: React.FC<{ label: string; value: string; testId: string }> = ({ label, value, testId }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard?.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {});
  };
  return (
    <div>
      <span className="text-[10px] uppercase tracking-wider text-slate-500 block">{label}</span>
      <div className="flex items-start gap-1.5">
        <code data-testid={testId} className="flex-1 min-w-0 break-all font-mono text-[11px] text-slate-300">
          {value}
        </code>
        <button
          type="button"
          onClick={handleCopy}
          className="p-1 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-400 shrink-0"
          title={`Copy ${label}`}
          aria-label={`Copy ${label}`}
        >
          {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
        </button>
      </div>
    </div>
  );
};

export const FairnessPanel: React.FC<FairnessPanelProps> = ({
  records,
  currentRound,
  getDealtHand,
  loadDeckDefinition = (name) => ApiService.getDeckDefinition(name),
}) => {
  const [expanded, setExpanded] = useState(false);
  const [verifications, setVerifications] = useState<Record<string, VerifyState>>({});

  if (records.length === 0) return null;

  const sorted = [...records].sort((a, b) => b.round_number - a.round_number);
  const active = sorted.filter((r) => !r.revealed);
  const revealed = sorted.filter((r) => r.revealed);
  const current = records.find((r) => r.round_number === currentRound) ?? sorted[0];

  const runVerification = async (record: FairnessRecord) => {
    const key = recordKey(record);
    if (!isWebCryptoAvailable()) {
      setVerifications((v) => ({
        ...v,
        [key]: { status: 'error', message: 'Web Crypto is unavailable in this browser context (HTTPS or localhost required).' },
      }));
      return;
    }
    setVerifications((v) => ({ ...v, [key]: { status: 'running' } }));
    try {
      const definition = await loadDeckDefinition(record.deck_definition);
      const result = await verifyFairnessRecord(record, definition.cards);
      const snapshot = getDealtHand?.(record.round_number);
      const handMatches = snapshot && result.deckOrder ? handMatchesDeal(snapshot, result.deckOrder) : null;
      setVerifications((v) => ({ ...v, [key]: { status: 'done', result, handMatches } }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Verification failed to run';
      setVerifications((v) => ({ ...v, [key]: { status: 'error', message } }));
    }
  };

  const renderVerification = (record: FairnessRecord) => {
    const state = verifications[recordKey(record)];
    if (!state) return null;
    if (state.status === 'running') {
      return <p className="text-[11px] text-slate-400">Verifying…</p>;
    }
    if (state.status === 'error') {
      return <p className="text-[11px] text-rose-400">{state.message}</p>;
    }
    const { result, handMatches } = state;
    if (!result.supported) {
      return (
        <p className="text-[11px] text-amber-400">
          Unsupported algorithm: this client verifies {SUPPORTED_ALGORITHM} only.
        </p>
      );
    }
    const passed = result.commitmentValid && result.canonicalDeckValid && result.deckOrder !== null && handMatches !== false;
    return (
      <div data-testid={`fairness-result-${record.round_number}`} className="space-y-0.5 text-[11px]">
        <p className={passed ? 'font-bold text-emerald-400' : 'font-bold text-rose-400'}>
          {passed ? 'Verified' : 'Verification FAILED'}
        </p>
        <p className={result.commitmentValid ? 'text-slate-300' : 'text-rose-400'}>
          {result.commitmentValid ? 'Seed matches commitment (SHA-256)' : 'Seed does NOT match commitment'}
        </p>
        <p className={result.canonicalDeckValid ? 'text-slate-300' : 'text-rose-400'}>
          {result.canonicalDeckValid ? 'Canonical deck matches published hash' : 'Canonical deck does NOT match published hash'}
        </p>
        {result.deckOrder && (
          <p className={handMatches === false ? 'text-rose-400' : 'text-slate-300'}>
            {handMatches === null
              ? `Deck order re-derived (${result.deckOrder.length} cards); your dealt hand was not observed in this session`
              : handMatches
              ? 'Your dealt hand matches the committed deck'
              : 'Your dealt hand does NOT match the committed deck'}
          </p>
        )}
      </div>
    );
  };

  const renderRecord = (record: FairnessRecord) => (
    <div
      key={recordKey(record)}
      data-testid={`fairness-round-${record.round_number}`}
      className="p-3 rounded-xl bg-slate-950/40 border border-slate-800 space-y-2"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-white">Round {record.round_number}</span>
        {record.revealed ? (
          <span className="px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-bold uppercase">
            Revealed
          </span>
        ) : (
          <span className="px-2 py-0.5 rounded-md bg-sky-500/10 border border-sky-500/20 text-sky-300 text-[10px] font-bold uppercase">
            Committed — seed hidden
          </span>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
        <div>
          <span className="text-[10px] uppercase tracking-wider text-slate-500 block">Algorithm</span>
          <span className="font-mono text-slate-300 break-all">{record.algorithm}</span>
        </div>
        <div>
          <span className="text-[10px] uppercase tracking-wider text-slate-500 block">Deck definition</span>
          <span className="font-mono text-slate-300">{record.deck_definition}</span>
        </div>
      </div>
      <CopyableValue label="Commitment" value={record.commitment} testId={`fairness-commitment-${record.round_number}`} />
      {record.revealed && record.server_seed && (
        <>
          <CopyableValue label="Server seed" value={record.server_seed} testId={`fairness-seed-${record.round_number}`} />
          <button
            type="button"
            onClick={() => runVerification(record)}
            disabled={verifications[recordKey(record)]?.status === 'running'}
            className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-[11px] disabled:opacity-40"
          >
            Verify round {record.round_number}
          </button>
          {renderVerification(record)}
        </>
      )}
    </div>
  );

  return (
    <div className="mt-4 rounded-2xl glass-panel border border-slate-800/80 z-10">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left"
      >
        <span className="flex items-center gap-2 text-xs font-bold text-slate-200">
          <ShieldCheck className="w-4 h-4 text-amber-400" />
          Provably Fair
        </span>
        <span className="flex items-center gap-2 text-[11px] text-slate-400">
          Round {current.round_number}: {current.revealed ? 'Revealed' : 'Committed — seed hidden'}
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          {active.length > 0 && (
            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">Active round</span>
              {active.map(renderRecord)}
            </div>
          )}
          {revealed.length > 0 && (
            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">Revealed rounds</span>
              {revealed.map(renderRecord)}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
