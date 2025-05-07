import { ServerData } from '../types';
import api from '../API/Index';

export const listDatabases = async () => {
  const formData = new FormData();
  try {
    const response = await api.post<ServerData>(`/list_databases`, formData);
    return response;
  } catch (error) {
    console.log('Error listing databases:', error);
    throw error;
  }
};
