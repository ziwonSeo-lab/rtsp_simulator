#!/usr/bin/env python3
"""
TC 네트워크 시뮬레이션 수정사항 검증 스크립트

수정된 구현의 핵심 개념을 검증합니다:
1. 기존: 가상 veth 인터페이스 (효과 없음)
2. 수정: 실제 loopback 인터페이스 (실제 효과)
"""

import subprocess
import json

def show_tc_concept_comparison():
    """TC 설정 개념 비교"""
    print("=" * 60)
    print("🔧 TC 네트워크 시뮬레이션 구현 비교")
    print("=" * 60)
    
    print("\n📍 기존 구현 (문제가 있던 방식):")
    print("   - 가상 veth 인터페이스에 TC 적용")
    print("   - FFmpeg ↔ MediaMTX 트래픽과 분리됨")
    print("   - TC 효과 없음 (항상 0% 손실)")
    
    print("\n✅ 수정된 구현 (올바른 방식):")
    print("   - 실제 네트워크 인터페이스(lo)에 TC 적용")  
    print("   - FFmpeg ↔ MediaMTX 트래픽 경로에 직접 적용")
    print("   - 실제 패킷 손실/지연 효과")
    
    print("\n🏗️ 수정된 TC 아키텍처:")
    print("   lo 인터페이스:")
    print("   ├── HTB root qdisc (1:) - 대역폭 제어")
    print("   ├── HTB 클래스 (1:10~1:15) - 스트림별 대역폭")
    print("   ├── netem qdisc (20:~25:) - 스트림별 손실/지연")
    print("   └── 포트 필터 (1911~1916) - 트래픽 분류")

def show_stream_mapping():
    """스트림별 포트 및 TC 설정 매핑"""
    print("\n📋 스트림별 TC 설정 매핑:")
    print("   스트림  RTMP포트  TC클래스  netem핸들  설정된 조건")
    print("   ----  -------  -------  --------  -----------")
    
    with open('config/config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    for i, stream in enumerate(config['streams']):
        if stream['enabled']:
            stream_id = stream['stream_id']
            rtmp_port = stream['rtmp_port']
            tc_class = f"1:{stream_id + 10}"
            netem_handle = f"{stream_id + 20}:"
            
            conditions = []
            if stream['packet_loss'] > 0:
                conditions.append(f"{stream['packet_loss']}% 손실")
            if stream['network_delay'] > 0:
                conditions.append(f"{stream['network_delay']}ms 지연")
            if stream['network_jitter'] > 0:
                conditions.append(f"{stream['network_jitter']}ms 지터")
            if stream['bandwidth_limit'] > 0:
                conditions.append(f"{stream['bandwidth_limit']}Mbps 제한")
            
            condition_text = ", ".join(conditions) if conditions else "기준선"
            print(f"   {stream_id:3}    {rtmp_port:4}     {tc_class:5}    {netem_handle:6}   {condition_text}")

def show_testing_approach():
    """테스트 접근 방법 설명"""
    print("\n🧪 테스트 접근 방법:")
    print("   1. 기준선: FFmpeg → MediaMTX → RTSP 클라이언트")
    print("      예상: 0.00% 패킷 손실")
    print("")
    print("   2. TC 적용: sudo python3 src/server/rtsp_sender.py")
    print("      - lo 인터페이스에 HTB + netem 적용")
    print("      - 포트별 트래픽 필터링")
    print("      - 실제 패킷 손실/지연 효과")
    print("")
    print("   3. 검증 명령어:")
    print("      sudo tc qdisc show dev lo    # HTB + netem 확인")
    print("      sudo tc class show dev lo    # 클래스별 대역폭 확인")
    print("      sudo tc filter show dev lo   # 포트 필터 확인")

def show_expected_results():
    """예상 결과"""
    print("\n📊 예상 측정 결과:")
    print("   스트림 0 (기준선):      0.00% 손실률")
    print("   스트림 1 (2% 손실):    ~2.00% 손실률")
    print("   스트림 2 (5% 손실):    ~5.00% 손실률")
    print("   스트림 3 (8% 손실):    ~8.00% 손실률")
    print("   스트림 4 (10% 손실):  ~10.00% 손실률")
    print("   스트림 5 (15% 손실):  ~15.00% 손실률")

def check_current_tc_status():
    """현재 TC 상태 확인"""
    print("\n🔍 현재 TC 상태:")
    try:
        result = subprocess.run(['tc', 'qdisc', 'show', 'dev', 'lo'], 
                              capture_output=True, text=True)
        print(f"   lo 인터페이스: {result.stdout.strip()}")
        
        if 'htb' in result.stdout:
            print("   ✅ HTB qdisc 활성 - TC 시뮬레이션 실행 중")
        else:
            print("   ⭕ 기본 qdisc - TC 시뮬레이션 비활성")
            
    except Exception as e:
        print(f"   ❌ TC 상태 확인 실패: {e}")

def main():
    show_tc_concept_comparison()
    show_stream_mapping()
    show_testing_approach()
    show_expected_results()
    check_current_tc_status()
    
    print("\n" + "=" * 60)
    print("🎯 수정 완료: 가상 인터페이스 → 실제 네트워크 인터페이스")
    print("   이제 sudo 권한으로 실행하면 실제 네트워크 시뮬레이션 효과를 볼 수 있습니다!")
    print("=" * 60)

if __name__ == "__main__":
    main()