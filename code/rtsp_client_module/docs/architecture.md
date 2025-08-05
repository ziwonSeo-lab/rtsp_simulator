# RTSP Client Module 아키텍처

## 🎯 전체 시스템 흐름도

```mermaid
graph LR
    %% 입력
    A[RTSP 스트림들] 
    
    %% 처리 파이프라인
    B[📹 캡처 워커들<br/>멀티프로세스]
    C[🔍 블러 워커들<br/>AI 처리]
    D[💾 저장 워커들<br/>비디오 인코딩]
    E[📦 파일 이동<br/>SSD→HDD]
    
    %% 출력
    F[📁 최종 비디오 파일들]
    
    %% 모니터링
    G[📊 실시간 통계<br/>& 미리보기]
    
    %% 메인 흐름
    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    
    %% 모니터링 연결
    B -.-> G
    C -.-> G
    D -.-> G
    
    %% 스타일
    style A fill:#e3f2fd
    style B fill:#fff3e0
    style C fill:#f3e5f5
    style D fill:#e8f5e8
    style E fill:#fff8e1
    style F fill:#e0f2f1
    style G fill:#fce4ec
```

## 📊 전체 시스템 아키텍처

```mermaid
graph TD
    A[메인 프로세스 - SharedPoolRTSPProcessor] --> B[시스템 초기화]
    B --> C[리소스 모니터링 시작]
    C --> D[워커 프로세스들 생성]
    
    D --> E[캡처 워커 프로세스들]
    D --> F[블러 워커 프로세스들]
    D --> G[저장 워커 프로세스들]
    D --> H[파일 이동 워커 프로세스들]
    D --> I[파일 모니터 워커 프로세스]
    
    E --> J[RTSP 스트림 1]
    E --> K[RTSP 스트림 2]
    E --> L[RTSP 스트림 N]
    
    E --> M[블러 큐들]
    F --> N[저장 큐들]
    G --> O[임시 파일 저장]
    H --> P[최종 파일 저장]
    
    style A fill:#e1f5fe
    style E fill:#fff3e0
    style F fill:#f3e5f5
    style G fill:#e8f5e8
    style H fill:#fff8e1
    style I fill:#fce4ec
```

## 🔄 프로세스 간 데이터 흐름

```mermaid
flowchart TD
    subgraph "메인 프로세스"
        MP[SharedPoolRTSPProcessor]
        RM[ResourceMonitor]
        PP[PerformanceProfiler]
        SM[Statistics Manager]
    end
    
    subgraph "캡처 프로세스들"
        CP1[캡처 워커 1]
        CP2[캡처 워커 2]
        CPN[캡처 워커 N]
    end
    
    subgraph "블러 프로세스들"
        BP1[블러 워커 1]
        BP2[블러 워커 2]
        BPN[블러 워커 N]
    end
    
    subgraph "저장 프로세스들"
        SP1[저장 워커 1]
        SP2[저장 워커 2]
        SPN[저장 워커 N]
    end
    
    subgraph "2단계 저장 프로세스들"
        FM[파일 모니터]
        FMV1[파일 이동 워커 1]
        FMV2[파일 이동 워커 2]
    end
    
    subgraph "데이터 큐들"
        BQ1[블러 큐 1]
        BQ2[블러 큐 2]
        SQ1[저장 큐 1]
        SQ2[저장 큐 2]
        FMQ[파일 이동 큐]
        PQ[미리보기 큐]
    end
    
    subgraph "외부 소스들"
        RTSP1[RTSP 스트림 1]
        RTSP2[RTSP 스트림 2]
        RTSPN[RTSP 스트림 N]
    end
    
    subgraph "저장소"
        SSD[SSD 임시 저장소]
        HDD[HDD 최종 저장소]
    end
    
    %% 데이터 흐름
    RTSP1 --> CP1
    RTSP2 --> CP1
    RTSPN --> CP2
    
    CP1 --> BQ1
    CP1 --> BQ2
    CP2 --> BQ1
    CP2 --> BQ2
    
    BQ1 --> BP1
    BQ2 --> BP2
    
    BP1 --> SQ1
    BP1 --> PQ
    BP2 --> SQ2
    BP2 --> PQ
    
    SQ1 --> SP1
    SQ2 --> SP2
    
    SP1 --> SSD
    SP2 --> SSD
    
    SSD --> FM
    FM --> FMQ
    FMQ --> FMV1
    FMQ --> FMV2
    FMV1 --> HDD
    FMV2 --> HDD
    
    %% 통계 및 모니터링
    CP1 -.-> SM
    BP1 -.-> SM
    SP1 -.-> SM
    SM -.-> MP
    RM -.-> MP
    PP -.-> MP
```

## ⚙️ 워커 프로세스 생성 시퀀스

```mermaid
sequenceDiagram
    participant M as 메인 프로세스
    participant C as 캡처 워커들
    participant B as 블러 워커들
    participant S as 저장 워커들
    participant F as 파일 워커들
    participant R as 리소스 모니터
    
    M->>M: SharedPoolRTSPProcessor 초기화
    M->>M: 큐들 생성 (blur_queues, save_queues)
    M->>R: 리소스 모니터링 시작
    
    loop 캡처 워커 개수만큼
        M->>C: Process 생성 (rtsp_capture_process)
        M->>C: 프로세스 시작
        C->>C: RTSP 스트림들 순환 처리
    end
    
    loop 블러 워커 개수만큼
        M->>B: Process 생성 (blur_worker_process)
        M->>B: 프로세스 시작
        B->>B: 블러 큐들 순환 처리
    end
    
    loop 저장 워커 개수만큼
        M->>S: Process 생성 (save_worker_process)
        M->>S: 프로세스 시작
        S->>S: 저장 큐들 순환 처리
    end
    
    opt 2단계 저장 활성화시
        M->>F: 파일 모니터 프로세스 시작
        M->>F: 파일 이동 워커들 시작
        F->>F: SSD→HDD 파일 이동
    end
    
    M->>M: 모든 프로세스 실행 중
```

## 💾 2단계 저장 시스템

```mermaid
graph LR
    subgraph "1단계: SSD 임시 저장"
        S1[저장 워커]
        S2[임시 비디오 파일]
        S3[파일 완료 알림]
        
        S1 --> S2
        S2 --> S3
    end
    
    subgraph "2단계: HDD 최종 저장"
        F1[파일 모니터]
        F2[파일 이동 큐]
        F3[파일 이동 워커]
        F4[최종 저장소]
        
        F1 --> F2
        F2 --> F3
        F3 --> F4
    end
    
    S3 --> F1
    
    style S2 fill:#fff3e0
    style F4 fill:#e8f5e8
```

## 🚀 핵심 동작 원리

1. **📥 입력**: 여러 RTSP 스트림 동시 수신
2. **🔄 처리**: 캡처 → 블러링 → 저장 파이프라인
3. **⚡ 병렬화**: 각 단계별 멀티프로세스 처리
4. **💾 최적화**: SSD 임시저장 → HDD 최종저장
5. **📊 모니터링**: 실시간 통계 및 성능 추적

## 📋 핵심 특징

- **🔄 공유 워커 아키텍처**: 각 워커가 모든 스트림을 순환 처리
- **🚀 멀티프로세싱**: CPU 코어 활용 극대화  
- **💾 2단계 저장**: SSD→HDD 최적화된 저장 시스템
- **📈 실시간 모니터링**: 리소스 및 성능 지속 추적
- **🔧 모듈화 설계**: 독립적인 컴포넌트들로 구성

## 🎯 성능 특징

- **멀티프로세스**: CPU 코어 완전 활용
- **파이프라인**: 단계별 병렬 처리
- **큐 기반**: 프로세스 간 안전한 데이터 전달
- **2단계 저장**: I/O 병목 최소화
- **실시간 모니터링**: 성능 최적화 지원