/**
 * Health strip da Home (RDR-057).
 *
 * Componente puro e presentacional: recebe os itens já resolvidos pelo read
 * model e mostra cada estado com rótulo textual (nunca só cor).
 */

import type { CapabilityHealth } from "../contracts";
import { capabilityLabel, describeHealthState } from "../health/strip";

export interface HealthStripProps {
  readonly items: readonly CapabilityHealth[];
}

export function HealthStrip({ items }: HealthStripProps) {
  return (
    <ul className="health-strip" aria-label="Saúde do Radar">
      {items.map((item) => {
        const presentation = describeHealthState(item.state);
        return (
          <li
            key={item.capability}
            className={`health-item health-item--${presentation.tone}`}
            data-capability={item.capability}
            data-state={item.state}
          >
            <span className="health-item__capability">{capabilityLabel(item.capability)}</span>
            <span className="health-item__state">{presentation.label}</span>
            <span className="health-item__summary">{item.summary}</span>
          </li>
        );
      })}
    </ul>
  );
}
