import json
import pandas

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from .KnowledgeBase import KnowledgeBase
from .models import Rule

# Create your views here.
dataset = None
initialized = False
features = []
cornerstones = []


def initialize():
    global dataset
    global initialized
    global features
    if not initialized:
        print('Initializing Knowledgebase and dataset................')
        dataset = pandas.read_csv('rdr_core/core/datasets/animal_dataset.csv')
        features = list(dataset.columns)
        initialized = True
        KnowledgeBase.get_kb(features=features)
        load_cornerstones()


def index_view(request):
    initialize()
    global dataset
    global initialized
    global features

    return render(request, 'rdr_core/index.html', {
        'dataset': dataset,
        'features': features
    })


def cornerstones_view(request):
    initialize()
    global cornerstones
    global dataset
    column_names = features.copy()
    column_names = [column_name.capitalize() for column_name in column_names]
    column_names.append('Current Conclusion')

    return_obj = []
    for cornerstone in cornerstones:
        case = list(dataset.iloc[cornerstone[0]])[0:len(features)]
        temp = [cornerstone[2]]
        temp = temp + case + [cornerstone[1]]

        return_obj.append(temp)
    return render(request, 'rdr_core/cornerstones.html', {
        'column_names': column_names,
        'cornerstones': return_obj
    })


def rules_view(request):
    initialize()
    global features
    column_names = features.copy()
    column_names = [column_name.capitalize() for column_name in column_names]
    column_names = ['Go to If True',
                    'Go to If False', 'Rule no'] + column_names
    column_names.append('Conclusion')

    all_rules = Rule.objects.filter(is_stopping=False).order_by('id')
    return_object = []
    temp = []
    i = 0
    while i < len(all_rules) or temp:
        row = [''] * len(column_names)
        if len(temp) == 0:
            current_rule = all_rules[i]
            if i != len(all_rules)-1:
                next_parent_rule = all_rules[i+1].id
            else:
                next_parent_rule = "exit"
            i += 1
            if current_rule.is_stopping:
                continue
        else:
            current_rule = temp.pop(0)

        if current_rule.if_true:
            stopping_rule = Rule.objects.get(id=current_rule.if_true)
            while stopping_rule:
                temp.append(stopping_rule)
                if stopping_rule.if_false:
                    stopping_rule = Rule.objects.get(id=stopping_rule.if_false)
                else:
                    stopping_rule = None

        conditions = json.loads(current_rule.conditions)
        if current_rule.conclusion:
            row[-1] = current_rule.conclusion
        if current_rule.is_stopping:
            row[2] = f"({current_rule.id})"
        else:
            row[2] = current_rule.id

        row[0] = next_parent_rule
        row[1] = next_parent_rule

        if current_rule.if_true:
            row[0] = f"({current_rule.if_true})"

        elif current_rule.if_false:
            row[1] = f"({current_rule.if_false})"

        condition_keys = conditions.keys()
        for key in condition_keys:
            feature_index = features.index(key)
            condition = conditions[key]
            row[feature_index+3] = condition

        return_object.append(row)

    return_object[-1][0] = 'exit'
    return_object[-1][1] = 'exit'

    return render(request, 'rdr_core/rules.html', {
        'column_names': column_names,
        'rows': return_object
    })


def run_view(request):
    initialize()
    global dataset
    kb = KnowledgeBase.get_kb()
    dataset['conclusion'] = ""
    dataset['rules_evaluated'] = ""
    dataset['rules_fired'] = ""

    for index, row in dataset.iterrows():
        evaluation = kb.eval_case(list(row))
        dataset.loc[index,
                    'rules_evaluated'] = "->".join(map(str, evaluation[1]))
        dataset.loc[index, 'rules_fired'] = "->".join(map(str, evaluation[2]))
        if not evaluation[0]:
            break
        dataset.loc[index, 'conclusion'] = ', '.join(evaluation[0])

        if not match_target_conclusion(row['target'], evaluation[0]):
            break

    return HttpResponseRedirect(reverse('index-page'))


def reset_view(request):
    global initialized
    initialized = False
    return HttpResponseRedirect(reverse('index-page'))


def update_conclusion_view(request):
    data = json.loads(request.body)
    print(data)
    rule = Rule.objects.get(id=data['update_rule_no'])
    rule.conclusion = data['new_conclusion']
    rule.save()
    return JsonResponse({
        'error': False,
        'msg': f"Conclusion for Rule {data['update_rule_no']} has been updated successfully."
    })


class EvalTest(View):

    def get(self, request):
        global dataset
        dataset = dataset.assign(conclusion='Akash')
        print(dataset)
        return HttpResponseRedirect(reverse('index-page'))

    def post(self, request):
        KnowledgeBase.get_kb()
        print(request.POST)
        return HttpResponse('OK')


class EvaluateSingle(View):
    def get(self, request):
        global features
        global dataset
        msg = "No Rules found for the Case Please Add a new Rule Above"
        kb = KnowledgeBase.get_kb()
        idx = int(request.GET['index'])
        case = list(dataset.iloc[idx])
        try:
            evaluation = kb.eval_case(case)
        except SyntaxError as e:
            evaluation = False
            msg = type(e)
        except Exception as e:
            evaluation = False
            msg = type(e)

        print(evaluation)
        if evaluation[0]:
            return_obj = []
            conclusions, _, rules_fired = evaluation

            rules_tobe_sent = rules_fired.copy()

            for rule_no in rules_fired:
                rule = Rule.objects.get(id=rule_no)
                if rule.is_stopping:
                    rules_tobe_sent.remove(rule.id)
                    rules_tobe_sent.remove(rule.parent)

            for rule_no in rules_tobe_sent:
                temp_dict = create_rule_dictionary(rule_no)
                if temp_dict:
                    return_obj.append(temp_dict)
            return JsonResponse({
                'error': False,
                'eval': evaluation,
                'eval_data': return_obj
            })
        else:
            return JsonResponse({
                'error': False,
                'eval': False,
                'msg': msg
            })


class AddRule(View):
    def post(self, request):
        kb = KnowledgeBase.get_kb()
        rule_datas = json.loads(request.body)
        print(rule_datas)
        conditions = {}
        conclusion = None
        cornerstone = []
        parent = -1
        for key in rule_datas.keys():
            if key == 'parent':
                parent = rule_datas['parent']
                continue
            if key == 'case':
                cornerstone = rule_datas['case']
                continue
            if key == 'conclusion':
                if rule_datas['conclusion'].upper() != 'N/A':
                    conclusion = rule_datas['conclusion']
                continue
            if rule_datas[key] != '':
                temp = key
                idx = int(temp.replace('condition', ''))
                conditions[features[idx]] = rule_datas[key]

        conditions = json.dumps(conditions)

        print('conditions: ', conditions)
        print('conclusion: ', conclusion)
        print('cornerstone', cornerstone)
        stopping_rule = Rule(conditions=conditions, parent=parent,
                             is_stopping=True, cornerstone=cornerstone)
        new_rule = Rule(conditions=conditions,
                        conclusion=conclusion, cornerstone=cornerstone)

        if conclusion:
            # Evaluate and Add new Rule
            skip_check = (parent == -2)
            matched_rule_no = check_matching_cornerstone(new_rule)
            if skip_check:
                kb.add_rule(new_rule)
            elif matched_rule_no != -1:
                return JsonResponse({
                    'error': True,
                    'eval_data': create_rule_dictionary(matched_rule_no),
                    'msg': f"The rule matches with a different cornerstone. Do you want to update the conclusion of the relavent rule (Rule {matched_rule_no}) with the new Conclusion?"
                })
            else:
                kb.add_rule(new_rule)

        if parent > 0:
            print('Stopping Rule Added..........')
            kb.add_rule(stopping_rule)

        load_cornerstones()

        return JsonResponse({
            'error': False,
            'msg': 'Rule(s) Added to Knowledgebase Successfully!!'
        })


def check_matching_cornerstone(new_rule):
    global cornerstones
    global dataset
    kb = KnowledgeBase.get_kb()
    for cornerstone, conclusion, rule_no in cornerstones:
        case = list(dataset.iloc[cornerstone])
        evaluation = kb.eval_case(case, [new_rule])
        if evaluation[0]:
            return rule_no

    return -1


def load_cornerstones():
    print('Loading Cornerstones.......')
    global cornerstones
    cornerstones = []
    rules = Rule.objects.all()
    for rule in rules:
        if rule.is_stopping:
            continue
        cornerstones.append((rule.cornerstone, rule.conclusion, rule.id))


def create_rule_dictionary(rule_no):
    temp_dict = {}
    rule = Rule.objects.get(id=rule_no)
    if rule.is_stopping:
        return {}
    temp_dict['rule_no'] = rule_no
    temp_dict['cornerstone'] = list(map(str, list(dataset.iloc[rule.cornerstone])[
        0:len(features)]))
    temp_dict['conclusion'] = rule.conclusion
    return temp_dict


def match_target_conclusion(target, conclusion):
    target = target.strip().split(',')

    for single_conclusion in conclusion:
        if single_conclusion not in target:
            return False
    return True
