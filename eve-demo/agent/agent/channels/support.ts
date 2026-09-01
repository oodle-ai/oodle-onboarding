import { defineChannel, POST } from 'eve/channels';

// The audience is what decides whether the prompts and replies
// reach Oodle. eve reads an absent audience as `unknown` and
// withholds the messages, so a demo without this line shows
// correct token counts and cost against an empty transcript.
//
// Only classify a conversation public when it really is visible
// to a group, and only when the exporter is approved to receive
// its content.
export default defineChannel({
  metadata: () => ({ audience: 'public' as const }),
  routes: [
    POST('/chat/:threadId', async (request, { from, params }) => {
      const body = (await request.json()) as { message: string };
      const session = await from(params.threadId).send(body.message, {
        auth: null,
      });
      return Response.json({ sessionId: session.id, threadId: params.threadId });
    }),
  ],
});
