// ClunyBrainClient.swift — HTTP client for Kosistenz Ask widget
// Copy into Kosistenz project (e.g. Kosistenz/ClunyClient/ClunyBrainClient.swift)

import Foundation

// MARK: - Models

public struct ClunyHealth: Codable, Sendable {
    public let status: String
    public let brainReady: Bool
    public let message: String?
    public let ollamaOk: Bool
    public let docCount: Int
    public let chunkCount: Int

    enum CodingKeys: String, CodingKey {
        case status
        case brainReady = "brain_ready"
        case message
        case ollamaOk = "ollama_ok"
        case docCount = "doc_count"
        case chunkCount = "chunk_count"
    }
}

public struct KosistenzContextPayload: Codable, Sendable {
    public var date: String?
    public var deadlineTodos: [DeadlineTodo]?
    public var eventsToday: [CalendarEvent]?
    public var weeklyGoals: [String]?
    public var analytics: AnalyticsSnapshot?
    public var notes: String?

    public struct DeadlineTodo: Codable, Sendable {
        public var title: String
        public var due: String?
    }

    public struct CalendarEvent: Codable, Sendable {
        public var title: String
        public var start: String?
        public var end: String?
    }

    public struct GoalProgress: Codable, Sendable {
        public var goal: String
        public var percent: Double?
    }

    public struct AnalyticsSnapshot: Codable, Sendable {
        public var period: String?
        public var tasksCompleted: Int?
        public var tasksSlipped: Int?
        public var focusHours: Double?
        public var journalStreakDays: Int?
        public var goalProgress: [GoalProgress]?

        enum CodingKeys: String, CodingKey {
            case period
            case tasksCompleted = "tasks_completed"
            case tasksSlipped = "tasks_slipped"
            case focusHours = "focus_hours"
            case journalStreakDays = "journal_streak_days"
            case goalProgress = "goal_progress"
        }
    }

    enum CodingKeys: String, CodingKey {
        case date
        case deadlineTodos = "deadline_todos"
        case eventsToday = "events_today"
        case weeklyGoals = "weekly_goals"
        case analytics
        case notes
    }
}

public struct ClunySource: Codable, Sendable {
    public let label: String
    public let snippet: String
    public let docPath: String?
    public let chunkIndex: Int?

    enum CodingKeys: String, CodingKey {
        case label, snippet
        case docPath = "doc_path"
        case chunkIndex = "chunk_index"
    }
}

public struct ClunyChatResponse: Codable, Sendable {
    public let route: String
    public let answer: String
    public let toolCalls: [String]
    public let sources: [ClunySource]
    public let sessionId: String

    enum CodingKeys: String, CodingKey {
        case route, answer, sources
        case toolCalls = "tool_calls"
        case sessionId = "session_id"
    }
}

public struct ClunyProposeResponse: Codable, Sendable {
    public let proposals: [ClunyProposal]
    public let sources: [ClunySource]
}

public struct ClunyProposal: Codable, Sendable {
    public let title: String
    public let estimateMinutes: Int?
    public let due: String?
    public let keywords: [String]

    enum CodingKeys: String, CodingKey {
        case title, due, keywords
        case estimateMinutes = "estimate_minutes"
    }
}

public enum ClunyStreamEvent: Sendable {
    case meta(route: String, sessionId: String)
    case sources([ClunySource])
    case token(String)
    case done
}

// MARK: - Client

public struct ClunyBrainClient: Sendable {
    public let baseURL: URL
    public var token: String?

    public init(baseURL: URL = URL(string: "http://127.0.0.1:8787")!, token: String? = nil) {
        self.baseURL = baseURL
        self.token = token
    }

    private func request(path: String, method: String = "GET", body: Data? = nil) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token, !token.isEmpty {
            req.setValue(token, forHTTPHeaderField: "X-Cluny-Token")
        }
        req.httpBody = body
        return req
    }

    public func health() async throws -> ClunyHealth {
        let (data, resp) = try await URLSession.shared.data(for: request(path: "health"))
        try validate(resp)
        return try JSONDecoder().decode(ClunyHealth.self, from: data)
    }

    public func chat(
        question: String,
        context: String? = nil,
        contextJSON: KosistenzContextPayload? = nil,
        sessionId: String? = nil,
        collection: String? = nil
    ) async throws -> ClunyChatResponse {
        struct Body: Encodable {
            let question: String
            let context: String?
            let contextJson: KosistenzContextPayload?
            let sessionId: String?
            let collection: String?

            enum CodingKeys: String, CodingKey {
                case question, context, collection
                case contextJson = "context_json"
                case sessionId = "session_id"
            }
        }
        let payload = Body(
            question: question,
            context: context,
            contextJson: contextJSON,
            sessionId: sessionId,
            collection: collection
        )
        let body = try JSONEncoder().encode(payload)
        let (data, resp) = try await URLSession.shared.data(for: request(path: "chat", method: "POST", body: body))
        try validate(resp)
        return try JSONDecoder().decode(ClunyChatResponse.self, from: data)
    }

    /// Stream tokens for typing-indicator UI. Yields meta, sources, tokens, then done.
    public func chatStream(
        question: String,
        context: String? = nil,
        contextJSON: KosistenzContextPayload? = nil,
        sessionId: String? = nil
    ) async throws -> AsyncThrowingStream<ClunyStreamEvent, Error> {
        struct Body: Encodable {
            let question: String
            let context: String?
            let contextJson: KosistenzContextPayload?
            let sessionId: String?

            enum CodingKeys: String, CodingKey {
                case question, context
                case contextJson = "context_json"
                case sessionId = "session_id"
            }
        }
        let payload = Body(question: question, context: context, contextJson: contextJSON, sessionId: sessionId)
        let body = try JSONEncoder().encode(payload)
        var req = request(path: "chat/stream", method: "POST", body: body)
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")

        return AsyncThrowingStream { continuation in
            Task {
                do {
                    let (bytes, resp) = try await URLSession.shared.bytes(for: req)
                    try validate(resp)
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let payload = String(line.dropFirst(6))
                        if payload == "[DONE]" {
                            continuation.yield(.done)
                            continuation.finish()
                            return
                        }
                        guard let data = payload.data(using: .utf8) else { continue }
                        if let meta = try? JSONDecoder().decode(Meta.self, from: data), let sid = meta.sessionId {
                            continuation.yield(.meta(route: meta.route ?? "ask", sessionId: sid))
                        } else if let src = try? JSONDecoder().decode(SourcesWrap.self, from: data) {
                            continuation.yield(.sources(src.sources))
                        } else if let tok = try? JSONDecoder().decode(TokenWrap.self, from: data) {
                            continuation.yield(.token(tok.token))
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    public func propose(
        question: String,
        context: String? = nil,
        contextJSON: KosistenzContextPayload? = nil,
        collection: String? = nil
    ) async throws -> ClunyProposeResponse {
        struct Body: Encodable {
            let question: String
            let context: String?
            let contextJson: KosistenzContextPayload?
            let collection: String?

            enum CodingKeys: String, CodingKey {
                case question, context, collection
                case contextJson = "context_json"
            }
        }
        let payload = Body(
            question: question,
            context: context,
            contextJson: contextJSON,
            collection: collection
        )
        let body = try JSONEncoder().encode(payload)
        let (data, resp) = try await URLSession.shared.data(for: request(path: "propose", method: "POST", body: body))
        try validate(resp)
        return try JSONDecoder().decode(ClunyProposeResponse.self, from: data)
    }

    /// After Kosistenz saves a journal file to disk.
    public func indexJournalCopy(
        text: String,
        title: String,
        collection: String = "journal"
    ) async throws {
        struct Body: Encodable {
            let text: String
            let catalog: Bool
            let source: String
            let title: String
            let collection: String
        }
        let payload = Body(
            text: text,
            catalog: true,
            source: "kosistenz-journal",
            title: title,
            collection: collection
        )
        let body = try JSONEncoder().encode(payload)
        let (_, resp) = try await URLSession.shared.data(for: request(path: "ingest/text", method: "POST", body: body))
        try validate(resp)
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200 ... 299).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }

    private struct Meta: Decodable {
        let route: String?
        let sessionId: String?

        enum CodingKeys: String, CodingKey {
            case route
            case sessionId = "session_id"
        }
    }

    private struct SourcesWrap: Decodable { let sources: [ClunySource] }
    private struct TokenWrap: Decodable { let token: String }
}
