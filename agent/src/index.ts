import { chhayaAgent } from './agent.js';

async function main() {
  if (!process.env.GROQ_API_KEY) {
    console.error('Set GROQ_API_KEY to run the Mastra agent (open-weight llama-3.3-70b).');
    console.error('Without it, the FastAPI app falls back to its offline deterministic planner.');
    process.exit(1);
  }

  const prompt =
    process.argv.slice(2).join(' ') ||
    'Walk dadu to the clinic around 3 pm, he cannot take much sun.';

  console.log(`> ${prompt}\n`);
  const res = await chhayaAgent.generate(prompt, { maxSteps: 5 });
  console.log(res.text);
  const toolCalls = (res as any).toolCalls ?? [];
  if (toolCalls.length) {
    console.log('\nTool calls:');
    for (const call of toolCalls) {
      const name = call.toolName ?? call.payload?.toolName ?? 'tool';
      const args = call.args ?? call.payload?.args ?? {};
      console.log(` - ${name}(${JSON.stringify(args)})`);
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
