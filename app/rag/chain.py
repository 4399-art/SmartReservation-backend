from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI

from app.config import settings
from app.rag.vector_store import get_vector_store


PROMPT_TEMPLATE = """你是一个"智能实验室预约系统"的智能助手。请严格根据下面提供的参考文档内容来回答用户的问题。
如果参考文档中找不到相关信息，请直接说"抱歉，我在知识库中没有找到相关内容"，不要编造答案。

参考文档内容:
{context}

用户问题: {question}
"""


def _format_docs(docs) -> str:
    return "\n\n".join(doc.page_content for doc in docs)


def build_rag_chain():
    llm = ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=0.3,
    )

    vector_store = get_vector_store()
    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 4},
    )

    prompt = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)

    rag_chain = (
        {"context": retriever | _format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    return rag_chain


def ask_rag(question: str) -> str:
    chain = build_rag_chain()
    return chain.invoke(question)