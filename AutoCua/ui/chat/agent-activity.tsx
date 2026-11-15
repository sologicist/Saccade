import { useEffect, useState } from 'react';
import { ReasoningTrace } from '../components/sakani/ReasoningTrace';
import type { RuntimeTurn } from './runtime-store';

// Feed SakaniUI with public status summaries and execution steps only.
export function AgentActivity({ turn, running }: { turn?: RuntimeTurn; running: boolean }) {
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  if (!turn || (!running && !turn.updates?.length && !turn.tools.length)) return null;

  const end = running ? now : Date.parse(turn.endedAt || turn.at);
  const elapsed = Math.max(0, Math.floor((end - Date.parse(turn.at)) / 1000));
  const statuses = { pending: 'En attente', running: 'En cours', success: 'Terminé', error: 'Interrompu ou en erreur' };

  return <div className="agent-activity">
    <ReasoningTrace status={running ? 'streaming' : 'done'} elapsed={elapsed}
      open={open} onOpenChange={setOpen} streamingLabel="Agent running" regionLabel="Étapes de progression de l’agent">
      {(turn.updates || []).map((text, index) => <p key={`update-${index}`}>{text}</p>)}
      {turn.tools.map(tool => <p key={tool.id}>{`${tool.name} — ${statuses[tool.status]}`}</p>)}
      {!turn.updates?.length && !turn.tools.length && <p>Démarrage de l’agent…</p>}
    </ReasoningTrace>
  </div>;
}
