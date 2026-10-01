from openai import OpenAI

client = OpenAI(
  base_url = "https://integrate.api.nvidia.com/v1",
  api_key = "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"
)


completion = client.chat.completions.create(
  model="deepseek-ai/deepseek-v4-flash-0731",
  messages=[{"role":"user","content":"Write a limerick about the wonders of GPU computing."}],
  temperature=1,
  top_p=0.95,
  max_tokens=16384,
  extra_body={"chat_template_kwargs":{"thinking":True,"reasoning_effort":"high"}},
  stream=False
)

reasoning = getattr(completion.choices[0].message, "reasoning", None) or getattr(completion.choices[0].message, "reasoning_content", None)
if reasoning:
  print("--- REASONING ---")
  print(reasoning)
  print("-----------------")
print(completion.choices[0].message.content)
