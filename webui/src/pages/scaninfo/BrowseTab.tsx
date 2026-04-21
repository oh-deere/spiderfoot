import { useState } from 'react';
import { EventList } from './EventList';
import { EventTypeList } from './EventTypeList';
import type { ScanSummaryRow } from '../../types';

export function BrowseTab({ id }: { id: string }) {
  const [selected, setSelected] = useState<ScanSummaryRow | null>(null);

  if (!selected) {
    return <EventTypeList id={id} onSelect={setSelected} />;
  }

  return (
    <EventList
      id={id}
      eventType={selected.typeId}
      onBack={() => setSelected(null)}
      backLabel="All event types"
      headerTitle={selected.typeLabel}
    />
  );
}
