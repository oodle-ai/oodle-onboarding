// Send one message to the trip planner and print its reply.
//
//   node scripts/chat.mjs <conversation-id> "<message>"
//
// Reusing a conversation id continues the same Flue conversation, so
// every turn of it shares one gen_ai.conversation.id in Oodle.
import { createFlueClient } from '@flue/sdk';

const [id = 'demo-trip', message = 'Plan a day in Lisbon.'] = process.argv.slice(2);
const base = process.env.AGENT_URL ?? `http://localhost:${process.env.PORT ?? 8099}`;

const conversation = createFlueClient({ url: `${base}/agents/trip-planner/${id}` });
const admission = await conversation.send({ message: { kind: 'user', body: message } });
console.log(`conversation: ${id}`);
console.log(`submission:   ${admission.submissionId}`);
console.log('');

try {
  const reply = await conversation.read(admission);
  console.log(reply.text);
} catch (error) {
  // A failed run still sends its trace: the failed span shows the
  // error in Oodle.
  const reason = error?.error?.meta?.reason ?? error?.message ?? String(error);
  console.error(`The agent run failed: ${reason}`);
  process.exitCode = 1;
}
