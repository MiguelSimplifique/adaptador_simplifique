function buildPrompt(messages) {
  const system = messages.find(msg => msg.role === 'system')?.content || '';
  const history = messages
    .filter(msg => msg.role === 'user' || msg.role === 'assistant')
    .map(msg => `${msg.role === 'user' ? 'Usuário' : 'Assistente'}: ${msg.content}`)
    .join('\n');

  return {
    system,
    history,
    finalPrompt: `${system}\n\nHistórico:\n${history}`,
  };
}

module.exports = { buildPrompt };
