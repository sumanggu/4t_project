from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
import boto3
import numpy as np
from botocore.exceptions import NoCredentialsError
import json
import re
from django.views.decorators.csrf import csrf_exempt
from io import StringIO
from .forms import KnowledgeSystemForm
import pandas as pd
import datetime
import importlib.util
import pickle
import os
import dask.dataframe as dd
import sys
import time
import io
import logging

logger = logging.getLogger(__name__)
sys.setrecursionlimit(10000)

s3 = boto3.client('s3')
athena_client = boto3.client('athena')

def get_csv_from_s3(bucket_name, key):
    try:
        response = s3.get_object(Bucket=bucket_name, Key=key)
        data = response['Body'].read().decode('utf-8')
        csv_data = pd.read_csv(io.StringIO(data))
        return csv_data
    
    except NoCredentialsError:
        print("No AWS credentials found.")
        return None

def save_new_data_to_s3(new_data, user_id, bucket_name, folder_name='student'):
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_key = f'{folder_name}/{user_id}_{now}.csv'   
    try:
        new_data_dask = dd.from_pandas(new_data, npartitions=1)
        csv_buffer = StringIO()
        new_data_dask.compute().to_csv(csv_buffer, index=False)

        s3.put_object(Bucket=bucket_name, Key=file_key, Body=csv_buffer.getvalue())
        logger.info(f'New data saved to S3 as {file_key}')
    except Exception as e:
        logger.error(f"Error saving new data to S3: {e}")


def query_athena(student_id, bucket_name, output_location, database='4t_db_test'):

    query = f"""
    SELECT *
    FROM student
    WHERE user_id = '{student_id}'
    """

    try:
        logger.info(f"Starting Athena query for student_id: {student_id}")
        response = athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': database},
            ResultConfiguration={'OutputLocation': f'{output_location}'},
            WorkGroup='primary'
        )
    except Exception as e:
        logger.error(f"Error starting Athena query: {e}")
        raise RuntimeError(f"Error starting Athena query: {e}")

    query_execution_id = response['QueryExecutionId']
    logger.info(f"Query Execution ID: {query_execution_id}")

    while True:
        query_status = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
        status = query_status['QueryExecution']['Status']['State']
        logger.info(f"Current Query Status: {status}")
        
        if status == 'SUCCEEDED':
            logger.info("Athena query succeeded")
            break
        elif status == 'FAILED':
            error_reason = query_status['QueryExecution']['Status']['StateChangeReason']
            logger.error(f"Athena query failed: {error_reason}")
            raise Exception(f'Athena query failed: {error_reason}')
        else:
            time.sleep(5)

    result_s3_path = f"{output_location}{query_execution_id}.csv"
    logger.info(f"Athena 쿼리 결과 파일 경로: {result_s3_path}")

    bucket_name, key = parse_s3_path(result_s3_path)
    
    try:
        logger.info(f"Attempting to retrieve query result from S3: bucket={bucket_name}, key={key}")
        obj = s3.get_object(Bucket=bucket_name, Key=key)
        data = obj['Body'].read().decode('utf-8')
        user_data = pd.read_csv(StringIO(data))
        logger.info(f"Retrieved {len(user_data)} rows for student ID {student_id}")
        logger.debug(f"First few rows of data:\n{user_data.head()}")
        return user_data
    except Exception as e:
        logger.error(f"Error retrieving data from S3: {e}")
        raise Exception(f"Error retrieving data from S3: {e}")

def load_quiz_from_s3(knowledge_unit):
    bucket_name = 'preprocessing-4t'
    key = 'preprocessed data/Question.csv'
    
    question = get_csv_from_s3(bucket_name, key)

    questions = []
    answers = []

    q= question[question['skill_id']==knowledge_unit]    

    for i in range(10):
        questions.append(q['Question'].values[i])
        answers.append(q['Answer'].values[i])
    
    logger.info(f"불러온 문제: {questions}, 정답: {answers}")
    
    return questions, answers

@csrf_exempt
def knowledge_form_view(request):
    if request.method == 'POST':
        if request.content_type == 'application/json':
            try:
                logger.info(f"Request content type: {request.content_type}")
                logger.info(f"Request body before JSON parse: {request.body}")

                data = json.loads(request.body)
                student_id = data.get("student_id")
                knowledge_unit = data.get("knowledge_unit")

                if not student_id or not knowledge_unit:
                    return JsonResponse({'error': 'Missing student_id or knowledge_unit'}, status=400)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        else:
            form = KnowledgeSystemForm(request.POST)
            if form.is_valid():
                student_id = form.cleaned_data['student_id']
                knowledge_unit = float(form.cleaned_data['knowledge_unit'])
            else:
                return JsonResponse({'error': 'Invalid form data'}, status=400)
            
        bucket_name = 'preprocessing-4t'
        key = 'preprocessed data/chunjae.csv'

        chunjae = get_csv_from_s3(bucket_name, key)

        chun = chunjae[chunjae['s_id']==knowledge_unit]
        in_skill_s = chun['s_nm'].values[0]
        in_skill_l = chun['l_nm'].values[0]
        in_se_1 = chun['se_1'].values[0]
        in_se_1 = in_se_1.astype(str)
        in_se_2 = chun['se_2'].values[0]
        in_se_2 = in_se_2.astype(str)

        questions, answers = load_quiz_from_s3(knowledge_unit)

        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'student_id': student_id,
                'knowledge_unit': knowledge_unit,
                'in_skill_s' : in_skill_s,
                'in_skill_l':in_skill_l,
                'in_se_1':in_se_1,
                'in_se_2':in_se_2,
                'questions': questions,
                'answers': answers,
            })
        else:
            return render(request, 'solve_questions.html', {
                'questions': questions,
                'student_id': student_id,
                'knowledge_unit': knowledge_unit,
                'in_skill_s' : in_skill_s,
                'in_skill_l':in_skill_l,
                'in_se_1':in_se_1,
                'in_se_2':in_se_2
            })

    if request.method == 'GET':
        form = KnowledgeSystemForm()
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'message': 'Use POST to submit data'}, status=400)
        else:
            return render(request, 'knowledge_form.html', {'form': form})

def load_pickle_from_s3(bucket_name, s3_key):
    response = s3.get_object(Bucket=bucket_name, Key=s3_key)
    pkl_data = pickle.loads(response['Body'].read())
    return pkl_data


def load_graph_and_model_from_s3(bucket_name, s3_key):
    response = s3.get_object(Bucket=bucket_name, Key=s3_key)
    graph, graph_model, concept_num = pickle.loads(response['Body'].read())
    return graph, graph_model, concept_num

def download_model_from_s3(bucket_name, s3_key):
    response = s3.get_object(Bucket=bucket_name, Key=s3_key)
    model_data = response['Body'].read()
    logger.info(f"Model data size: {len(model_data)} bytes")
    return model_data

def parse_s3_path(s3_path):
    match = re.match(r's3://([^/]+)/(.+)', s3_path)
    if match:
        bucket_name = match.group(1)
        key = match.group(2)
        return bucket_name, key
    else:
        raise ValueError("S3 경로가 올바르지 않습니다.")

@csrf_exempt
def submit_answers(request):
    if request.method == 'POST':
        logger.info(f"Request Headers: {request.headers}")
        logger.info(f"Request Body: {request.body}")
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body.decode('utf-8'))
                student_id = data.get("student_id")
                knowledge_unit = data.get("knowledge_unit")
                answers = {k: v for k, v in data.items() if k.startswith("answer_")}
            else:
                student_id = request.POST.get("student_id")
                knowledge_unit = request.POST.get("knowledge_unit")
                answers = {f"answer_{i}": request.POST.get(f"answer_{i}") for i in range(1, 11)}

            if not knowledge_unit:
                logger.error("knowledge_unit 값이 없습니다.")
                return JsonResponse({"error": "knowledge_unit 값이 없습니다."}, status=400)

            knowledge_unit = float(knowledge_unit)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON 또는 값 변환 오류: {e}")
            return JsonResponse({"error": "Invalid JSON data or knowledge_unit 값 변환 중 오류가 발생했습니다."}, status=400)

        questions, correct_answers = load_quiz_from_s3(knowledge_unit)

        results = []
        for i, correct_answer in enumerate(correct_answers, start=1):
            user_answer = answers.get(f"answer_{i}", "")
            results.append(1 if user_answer and user_answer.lower() == correct_answer.lower() else 0)

        logger.info(f"User answers: {answers}")
        logger.info(f"Results: {results}")

        new_data = pd.DataFrame({
            'user_id': [student_id] * len(results),
            'correct': results,
            'skill_id': [knowledge_unit] * len(results),
        })

        current_unix_time = int(time.time())
        time_interval = 1

        new_data['unix_time'] = [int(current_unix_time + i * time_interval) for i in range(len(new_data))]

        print(new_data.info())

        bucket_name = 'preprocessing-4t'
        processed_data_key = 'preprocessed data/skill.csv'

        skill = get_csv_from_s3(bucket_name, processed_data_key)

        new_data = new_data.merge(skill,
            left_on=['skill_id', 'correct'],
            right_on=['skill_id', 'correct'],
            how='left'
        )
        print(new_data)
        new_data = new_data.loc[:, ~new_data.columns.duplicated()]

        new_data = new_data[['user_id', 'correct','skill_id', 'skill','skill_with_answer','unix_time']]

        score = len(new_data[new_data['correct']==1])*10
        print(f'score: {score}')

        save_new_data_to_s3(new_data, student_id, bucket_name, folder_name='student')


        request.session['student_id'] = student_id
        request.session['knowledge_unit'] = knowledge_unit
        # GKT
        model_bucket_name = 'result-4t'
        model_key = 'gkt/gkt.py'
        gkt = load_model_from_s3(model_bucket_name, model_key, local_file_name='gkt.py')
        
        bucket_name = 'result-4t'
        s3_key = 'gkt/metadata.pkl'

        metadata = load_pickle_from_s3(bucket_name, s3_key)
        print(f'Model metadata.pkl downloaded from S3')
        
        args = metadata['args']

        bucket_name = 'result-4t'
        s3_key = 'gkt/saved_graph_model_and_concept_num.pkl'
        print(f'Model saved_graph_model_and_concept_num.pkl downloaded from S3')

        graph, graph_model, concept_num = load_graph_and_model_from_s3(bucket_name, s3_key)

        bucket_name = 'result-4t'
        model_s3_key = 'gkt/GKT-Dense.pt'
        model_data = download_model_from_s3(bucket_name, model_s3_key)

        if gkt is None:
            return JsonResponse({"error": "No model found"}, status=404)


        bucket_name = 'preprocessing-4t'
        output_location = 's3://preprocessing-4t/query/'

        user_data = query_athena(student_id, bucket_name, output_location)

        user_data = user_data.sort_values(by='unix_time')

        user = user_data[user_data['skill_id']==knowledge_unit]

        sk_score = (len(user[user['correct']==1])/len(user))*100
        sk_score = round(sk_score,2)
        print(f'sk_score: {sk_score}')

        print(f'user: {user_data.tail(15)}')

        sk, cor_per = gkt.run_model(user_data, student_id,args,graph, graph_model, concept_num,model_data)
        sk = int(sk) if isinstance(sk, np.int64) else sk
        cor_per = float(cor_per) if isinstance(cor_per, np.float64) else cor_per

        gkt_per = round(cor_per*100,2)

        # DeepFM
        model_bucket_name = 'result-4t'
        model_key = 'deepfm/deep.py'
        deep = load_model_from_s3(model_bucket_name, model_key, local_file_name='deep.py')
        
        if deep is None:
            return JsonResponse({"error": "No model found"}, status=404)

        deep = deep.dfm(user_data, cor_per)
        deep_list = deep.tolist()

        # cf
        model_bucket_name = 'result-4t'
        model_key = 'cf/cf.py'
        cf = load_model_from_s3(model_bucket_name, model_key, local_file_name='cf.py')

        bucket_name = 'result-4t'
        f_key = 'cf/merged_preprocessed_data.csv'
        c_key = 'cf/preprocessed_concept_relationships.csv'

        final_data = get_csv_from_s3(bucket_name, f_key)
        concept_df = get_csv_from_s3(bucket_name, c_key)

        if isinstance(concept_df, str):
            print("Error: concept_df가 DataFrame으로 로드되지 않았습니다.")
            return HttpResponse("Error: concept_df가 올바르게 로드되지 않았습니다.", status=500)

        
        if cf is None:
            return JsonResponse({"error": "No model found"}, status=404)
        
        cf = cf.run(student_id, float(knowledge_unit), cor_per,final_data, concept_df)

        if cf is None:
            print("Error: cf 데이터가 None입니다. 파일 경로나 데이터 소스를 확인하세요.")
            return HttpResponse("Error: 필요한 데이터가 없습니다.", status=500)

        if 'Review Skill ID' not in cf.columns:
            cf_list = []
        else:
            cf_list = cf['Review Skill ID'].tolist()

        know_list = list(set(deep_list) & set(cf_list))

        if know_list == []:
            deep_list = deep_list[:5]
            cf_list = cf_list[:5]
            know_list = list(set(set(deep_list) | set(cf_list)))

        print(f'mapping 전 know_list: {know_list}')

        bucket_name = 'preprocessing-4t'
        key = 'preprocessed data/data_lec.csv'
    
        lec = get_csv_from_s3(bucket_name, key)

        bucket_name = 'preprocessing-4t'
        key = 'preprocessed data/mapping.csv'

        mapping = get_csv_from_s3(bucket_name, key)


        skill_dict = dict(zip(mapping['skill_id'], mapping['skill']))
        know_list = list(map(skill_dict.get, know_list))
        print(f"know_list contents: {know_list}")

        # 최종 gkt

        model_bucket_name = 'result-4t'
        model_key = 'gkt/test_final.py'
        gkt_final = load_model_from_s3(model_bucket_name, model_key, local_file_name='test_final.py')

        sk_list = []
        per_list = []

        for i in know_list:
            try:
                sk_final, per = gkt_final.run_model(user_data, student_id, i, args, graph, graph_model, concept_num, model_data)
                if sk_final is not None and per is not None:
                    sk_list.append(sk_final)
                    per_list.append(per)
                else:
                    print(f"Warning: run_model returned None for sk_final or per with i={i}")
            except Exception as e:
                print(f"Error in run_model with i={i}: {e}")

        print(sk_list)
        print(per_list)

        if cor_per > 0.5:
            index = per_list.index(max(per_list))
        elif cor_per < 0.5:
            index = per_list.index(min(per_list))

        skill_final = sk_list[index]

        mapping_2 = mapping[mapping['skill']==skill_final]
        skill_final = mapping_2['skill_id'].values[0]

        print(f'skill_final: {skill_final}')

        skill_data = lec[lec['skill_id']==skill_final]

        result_lec = skill_data['mcode']
        result_lec_nm = skill_data['title']

        result_lec_list = result_lec.tolist()
        result_lec_nm_list = result_lec_nm.tolist()

        print(f'result_lec_list:{result_lec_list}')
        print(f'result_lec_nm_list:{result_lec_nm_list}')

        result_lec = [f"{b}({a})" for a, b in zip(result_lec_list, result_lec_nm_list)]

        bucket_name = 'preprocessing-4t'
        key = 'preprocessed data/chunjae.csv'

        chunjae = get_csv_from_s3(bucket_name, key)

        chun = chunjae[chunjae['s_id']==knowledge_unit]
        in_skill_s = chun['s_nm'].values[0]
        in_skill_l = chun['l_nm'].values[0]
        in_se_1 = chun['se_1'].values[0]
        in_se_1 = in_se_1.astype(str)
        in_se_2 = chun['se_2'].values[0]
        in_se_2 = in_se_2.astype(str)

        out_chun = chunjae[chunjae['s_id']==skill_final]
        out_skill_s = out_chun['s_nm'].values[0]
        out_skill_l = out_chun['l_nm'].values[0]
        out_se_1 = out_chun['se_1'].values[0]
        out_se_1 = out_se_1.astype(str)
        out_se_2 = out_chun['se_2'].values[0]
        out_se_2 = out_se_2.astype(str)

        if cor_per < 0.5:
            result = '복습'
            ment = '아래에 안내되는 단원을 다시 한 번 더 공부해볼까요?'
        elif cor_per > 0.5:
            result = '선행'
            ment = '아래에 안내되는 단원을 미리 공부해볼까요?'

        request.session['model_results'] = {
            'sk': sk,  # 입력한 스킬 아이디
            'in_skill_snm':in_skill_s, # 입력한 스킬 아이디 소단원명
            'in_skill_lnm':in_skill_l, # 입력한 스킬 아이디 대단원명
            'in_se_1':in_se_1,
            'in_se_2':in_se_2,
            'score':score,
            'gkt_per':gkt_per,
            'result':result,
            'ment':ment,
            "skill_final" : skill_final, # 추천되는 스킬 아이디
            'out_skill_snm':out_skill_s, # 추천되는 스킬 아이디 소단원명
            'out_skill_lnm':out_skill_l, # 추천되는 스킬 아이디 대단원명
            'out_se_1':out_se_1,
            'out_se_2':out_se_2,
            'sk_score':sk_score,
            'lec':result_lec   # 추천되는 강의(강의코드) 리스트
        }

        logger.info(f"Session data before redirect: {request.session}")

        print(f'know_type: {type(knowledge_unit)}')

        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                "student_id": student_id,
                "knowledge_unit": knowledge_unit,
                'in_skill_snm':in_skill_s,
                'in_skill_lnm':in_skill_l,
                'in_se_1':in_se_1,
                'in_se_2':in_se_2,
                'score':score,
                'sk_score':sk_score,
                'gkt_per':gkt_per,
                'result':result,
                'out_skill_snm':out_skill_s,
                'out_skill_lnm':out_skill_l,
                'out_se_1':out_se_1,
                'out_se_2':out_se_2,
                'lec':result_lec
            })
        else:
            return redirect('result_page')

    return redirect('home')

def load_model_from_s3(bucket_name, key, local_file_name):
    try:
        if os.path.exists(local_file_name):
            os.remove(local_file_name)

        s3.download_file(bucket_name, key, local_file_name)
        print(f'Model {local_file_name} downloaded from S3')

        if not os.path.exists(local_file_name):
            raise FileNotFoundError(f"{local_file_name} not found after download.")

        spec = importlib.util.spec_from_file_location("test_model", local_file_name)
        model_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model_module)

        return model_module
    except Exception as e:
        print(f'Error loading model from S3: {e}')
        return None

logger = logging.getLogger(__name__)

def result_page(request):
    student_id = request.GET.get('student_id') or request.session.get('student_id')
    knowledge_unit = request.GET.get('knowledge_unit') or request.session.get('knowledge_unit')
    
    model_results = request.session.get('model_results')

    if not student_id or not knowledge_unit or not model_results:
        logger.error("Required data is missing from the session.")
        return HttpResponse("Error: Required data is missing.", status=400)

    logger.info(f"Received student_id: {student_id}")

    response_data = {
        'student_id': student_id, # 학생 아이디
        'knowledge_unit': knowledge_unit, # 입력한 지식체계(천재)
        'sk': model_results['sk'],  # 입력한 지식체계(인덱스)
        'in_skill_snm':model_results['in_skill_snm'], # 입력한 스킬 아이디 소단원명
        'in_skill_lnm':model_results['in_skill_lnm'], # 입력한 스킬 아이디 대단원명
        'in_se_1':model_results['in_se_1'],
        'in_se_2':model_results['in_se_2'],
        'score':model_results['score'],
        'gkt_per':model_results['gkt_per'],
        'result':model_results['result'], # 판단 결과
        'ment':model_results['ment'],
        "skill_final" : model_results['skill_final'], # 추천되는 스킬 아이디
        'out_skill_snm':model_results['out_skill_snm'], # 추천되는 스킬 아이디 소단원명
        'out_skill_lnm':model_results['out_skill_lnm'], # 추천되는 스킬 아이디 대단원명
        'out_se_1':model_results['out_se_1'],
        'out_se_2':model_results['out_se_2'],
        'sk_score':model_results['sk_score'],
        'lec':model_results['lec']   # 추천되는 강의(강의코드) 리스트


    }

    if request.headers.get('Accept') == 'application/json':
        return JsonResponse(response_data)
    else:
        return render(request, 'result_page.html', response_data)

def home_view(request):
    return render(request, 'home.html')