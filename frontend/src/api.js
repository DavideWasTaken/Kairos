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

export const askFinancialChat = async (message, ticker, history = []) => {
    try {
        const response = await axios.post(`${API_URL}/chat`, {
            message,
            ticker,
            history,
        });
        return response.data;
    } catch (error) {
        console.error("Chat Error:", error);
        throw error;
    }
};
