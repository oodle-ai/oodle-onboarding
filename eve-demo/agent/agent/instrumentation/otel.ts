import { otel } from 'eve/instrumentation/otel';

export default otel({
  // eve withholds the messages for every conversation its
  // channel does not classify as public. Tokens, cost and the
  // span tree arrive without this; the transcript does not.
  tracePolicy: () => ({
    emit: true,
    recordInputs: true,
    recordOutputs: true,
  }),
});
