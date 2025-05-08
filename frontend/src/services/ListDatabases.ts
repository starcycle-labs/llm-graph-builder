// import { ServerData } from '../types';
import api, { createDefaultFormData } from '../API/Index';

interface DatabaseListResponse {
  status: string;
  data: {
    databases: string[];
  };
  error?: string;
}

export const listDatabases = async (uri: string, userName: string, password: string) => {
  console.log('3. listDatabases called with:', { uri, userName, password });
  const formData = createDefaultFormData({
    uri,
    userName,
    password,
    database: 'neo4j',
    email: '',
  });
  try {
    console.log('4. Making API call to /list_databases');
    const response = await api.post<DatabaseListResponse>(`/list_databases`, formData);
    console.log('5. API response:', response);
    return response;
  } catch (error) {
    console.log('Error listing databases:', error);
    throw error;
  }
};
