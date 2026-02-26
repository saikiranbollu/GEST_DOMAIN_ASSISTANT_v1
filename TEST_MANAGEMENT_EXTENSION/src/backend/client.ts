import axios, { AxiosInstance } from 'axios';

interface GenerateTestRequest {
    module: string;
    description: string;
    additional_notes?: string;
    llm_model?: string;
}

interface TestGenerationResult {
    test_id: string;
    status: string;
    module: string;
    description: string;
    compliance_score: number;
    generation_time: {
        total_seconds: number;
        display: string;
    };
    output_file: string;
    test_code: string;
    rag_context: {
        functions_count: number;
        structs_count: number;
        enums_count: number;
        requirements_count: number;
    };
    kg_context: {
        dependency_count: number;
        dependencies: any;
    };
    generation_result: any;
    llm_enhancement: {
        available: boolean;
        model?: string;
        enhanced_code?: string;
        llm_result?: any;
        llm_prompt?: string;
        enum_resolver_prompt?: string;
    };
    timestamp: string;
}

interface LLMModel {
    name: string;
    isCurrent: boolean;
}

/**
 * Client for communicating with the FastAPI backend
 */
export class BackendClient {
    private client: AxiosInstance;
    private backendUrl: string;
    
    constructor(backendUrl: string) {
        this.backendUrl = backendUrl;
        this.client = axios.create({
            baseURL: backendUrl,
            timeout: 120000
        });
    }
    
    /**
     * Check if backend is reachable
     */
    async checkHealth(): Promise<boolean> {
        try {
            const response = await this.client.get('/health');
            return response.status === 200;
        } catch (error: unknown) {
            console.error('Health check failed:', error);
            return false;
        }
    }
    
    /**
     * Generate a test
     */
    async generateTest(request: GenerateTestRequest): Promise<TestGenerationResult> {
        try {
            const response = await this.client.post<TestGenerationResult>('/generate_test', request);
            return response.data;
        } catch (error: unknown) {
            if (axios.isAxiosError(error)) {
                throw new Error(`Backend error: ${error.response?.data?.detail || error.message}`);
            }
            throw error;
        }
    }
    
    /**
     * Get available LLM models
     */
    async getAvailableModels(): Promise<LLMModel[]> {
        try {
            const response = await this.client.get('/llm/models');
            const data = response.data;
            
            return data.models?.map((name: string) => ({
                name,
                isCurrent: name === data.current_model
            })) || [];
        } catch (error: unknown) {
            console.error('Failed to get models:', error);
            return [];
        }
    }
    
    /**
     * Update available models on the backend
     */
    async updateAvailableModels(models: string[]): Promise<void> {
        try {
            await this.client.post('/llm/update-models', { models });
        } catch (error: unknown) {
            console.error('Failed to update models:', error);
            throw error;
        }
    }
    
    /**
     * Select an LLM model
     */
    async selectModel(model: string): Promise<boolean> {
        try {
            const response = await this.client.post(`/llm/select-model?model=${encodeURIComponent(model)}`);
            return response.status === 200;
        } catch (error: unknown) {
            console.error('Failed to select model:', error);
            return false;
        }
    }
    
    /**
     * Query functions from RAG
     */
    async queryFunctions(module: string, intent: string): Promise<any[]> {
        try {
            const response = await this.client.post('/query/functions', {
                module,
                intent
            });
            return response.data;
        } catch (error: unknown) {
            console.error('Failed to query functions:', error);
            return [];
        }
    }
    
    /**
     * Query dependencies from KG
     */
    async queryDependencies(module: string, function_name: string): Promise<any[]> {
        try {
            const response = await this.client.post('/query/dependencies', {
                module,
                function_name
            });
            return response.data;
        } catch (error: unknown) {
            console.error('Failed to query dependencies:', error);
            return [];
        }
    }
    
    /**
     * Get available modules (dynamically discovered from ingested data)
     */
    async getAvailableModules(): Promise<string[]> {
        try {
            const response = await this.client.get('/modules');
            return response.data?.modules || [];
        } catch (error: unknown) {
            console.error('Failed to get modules:', error);
            return [];
        }
    }

    /**
     * Apply Stage 1 enum resolution to skeleton code.
     * Sends resolved enum values (from gpt-5-mini) to backend for substitution.
     */
    async applyEnumResolution(sampleTestCode: string, resolvedValues: Record<string, string>): Promise<string> {
        try {
            const response = await this.client.post('/apply_enum_resolution', {
                sample_test_code: sampleTestCode,
                resolved_values: resolvedValues
            });
            return response.data?.resolved_code || sampleTestCode;
        } catch (error: unknown) {
            console.error('Failed to apply enum resolution:', error);
            return sampleTestCode;  // Fallback: return original skeleton
        }
    }
}
