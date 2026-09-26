import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || '/api';

export const fetchHealth = async () => (await axios.get(`${API_URL}/health`)).data;

export const analyzeStock = async (ticker, period = '3mo', dcfProfile = 'base') => {
    try {
        const response = await axios.get(`${API_URL}/analyze/${ticker}`, {
            params: { period, dcf_profile: dcfProfile }
        });
        return response.data;
    } catch (error) {
        console.error("API Error:", error);
        throw error;
    }
};

export const searchAssets = async (query) => {
    try {
        const response = await axios.get(`${API_URL}/search`, {
            params: { q: query }
        });
        return response.data;
    } catch (error) {
        console.error("Search Error:", error);
        return [];
    }
};

export const formatApiError = (error, fallback = 'Request failed.') => {
    const detail = error?.response?.data?.detail;
    if (Array.isArray(detail)) return `${fallback} Check the request fields.`;
    return typeof detail === 'string' && detail.trim() ? detail.trim().slice(0, 300) : fallback;
};

export const buildChatPayload = (message, ticker, history = [], dcfProfile = 'base') => ({
    message,
    ticker,
    dcf_profile: dcfProfile,
    history: history.slice(-8).map(({ role, content }) => ({ role, content: content.slice(0, 2000) })),
});

export const askFinancialChat = async (message, ticker, history = [], dcfProfile = 'base') => {
    try {
        const response = await axios.post(`${API_URL}/chat`, buildChatPayload(message, ticker, history, dcfProfile));
        return response.data;
    } catch (error) {
        console.error("Chat Error:", error);
        throw error;
    }
};
