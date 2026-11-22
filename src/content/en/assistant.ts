import type { AssistantCopy } from '../zh/assistant';

/** English: site-wide floating estimate assistant. */
const assistant: AssistantCopy = {
  suggestions: [
    'What should I prepare for a quote?',
    'What costs does a quote include?',
    'How do I reach the support team?',
  ],
  intro:
    'I am the inquiry assistant for business questions: service scope, the China-Vietnam route process, documents and lead times. To calculate distance and freight, use the Quote Assistant on the quote page (/quote), which runs on the route and rate engine.',
  actions: {
    docDetail: 'View cost breakdown',
    reMatch: 'Recalculate with another vehicle',
    reMatchPrompt: 'Recalculate with a full truck / 17.5 m low-bed',
    vehicleMatch: 'Open vehicle matching',
    submitQuote: 'Submit a formal inquiry',
  },
  status: {
    idle: 'No calculation tool called yet',
    reading: 'Reading the question…',
    calling: 'Calling: {label}',
    callingGeneric: 'Calling a calculation tool…',
    done: 'Calculation tool returned results',
  },
  ui: {
    clear: 'Clear conversation',
    typing: 'Drafting…',
    placeholder: 'E.g. Nanning → Hanoi, 20 t, full truck',
    askAria: 'Ask the inquiry assistant',
    sending: 'Drafting…',
    send: 'Send',
    note: 'Preliminary estimate · Not a formal quote · No lead-time commitment',
  },
};

export default assistant;
